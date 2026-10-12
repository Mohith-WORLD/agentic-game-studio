"""
Unit tests for StudioOrchestrator and Deterministic Self-Repair Loop.
Tests run completely offline with mocked LLM/task execution.
"""

from typing import Any, List
import pytest

from config.settings import Settings
from sandbox.executor import ExecutionResult, MockExecutor, DockerExecutor
from studio.agents import create_llm, create_game_designer, create_game_developer, create_qa_engineer
from studio.orchestrator import StudioOrchestrator, StudioResult


VALID_GAME_CODE = '''import asyncio
import os
import sys
import pygame

async def main():
    pygame.init()
    screen = pygame.display.set_mode((640, 480))
    clock = pygame.time.Clock()
    running = True
    frames = 0
    smoke_test = os.getenv("SMOKE_TEST") == "1" or "--smoke-test" in sys.argv
    max_frames = int(os.getenv("SMOKE_TEST_FRAMES", "60"))

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        screen.fill((0, 0, 0))
        pygame.display.flip()
        clock.tick(60)
        frames += 1
        if smoke_test and frames >= max_frames:
            running = False
        await asyncio.sleep(0)
    pygame.quit()
    return 0

if __name__ == "__main__":
    asyncio.run(main())
'''

SYNTAX_ERROR_CODE = '''import asyncio
import pygame

async def main()  # Missing colon
    pass
'''

MISSING_DUAL_RUNTIME_CODE = '''import pygame

def main():
    pass

if __name__ == "__main__":
    main()
'''


class MockTaskRunner:
    """Configurable mock runner that intercepts agent tasks and returns controlled responses."""

    def __init__(self, developer_responses: List[str]):
        self.developer_responses = list(developer_responses)
        self.dev_call_count = 0
        self.tasks_received: List[Any] = []

    def __call__(self, agent: Any, task: Any) -> str:
        self.tasks_received.append(task)
        role = getattr(agent, "role", "")

        if "Designer" in role:
            return "## Game Design Document\n- Title: Retro Dodger\n- Controls: Arrows"
        elif "Developer" in role:
            self.dev_call_count += 1
            if self.developer_responses:
                return self.developer_responses.pop(0)
            return "```python\n# fallback\n```"
        elif "QA" in role:
            return "## QA Audit Report\nVerification completed."
        return "Generic response"


class SequentialMockExecutor(MockExecutor):
    """Mock executor that yields a sequence of results across successive runs."""

    def __init__(self, sequence: List[ExecutionResult]):
        super().__init__(simulated_status="PASS")
        self.sequence = list(sequence)
        self.call_count = 0

    def run(self, code: str, smoke_frames: int = 60, timeout_seconds: int = 10) -> ExecutionResult:
        self.call_count += 1
        if self.sequence:
            return self.sequence.pop(0)
        return ExecutionResult(status="PASS", returncode=0, frames_rendered=smoke_frames)


# =========================================================================
# 1. Successful Orchestration Tests
# =========================================================================

def test_successful_orchestration_with_docker_unavailable():
    """Verify happy path when Docker is unavailable: reports NOT_TESTED and succeeds statically."""
    mock_runner = MockTaskRunner(developer_responses=[f"```python\n{VALID_GAME_CODE}\n```"])
    # Real DockerExecutor fail-closes to NOT_TESTED when docker is missing on host
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=DockerExecutor(),
        task_runner=mock_runner,
    )

    result = orchestrator.run("Retro dodge game")

    assert result.success is True
    assert result.repair_attempts == 0
    assert result.validation_result.is_valid is True
    assert result.execution_result.status == "NOT_TESTED"
    assert "STATICALLY_VALID_EXECUTION_UNTESTED" in result.status_summary
    assert mock_runner.dev_call_count == 1  # 1 initial generation, 0 repairs


def test_successful_orchestration_with_mock_pass_executor():
    """Verify happy path with an active executor returning PASS."""
    mock_runner = MockTaskRunner(developer_responses=[f"```python\n{VALID_GAME_CODE}\n```"])
    mock_executor = MockExecutor(simulated_status="PASS", simulated_returncode=0, frames=60)
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=mock_executor,
        task_runner=mock_runner,
    )

    result = orchestrator.run("Pong game")

    assert result.success is True
    assert result.repair_attempts == 0
    assert result.execution_result.status == "PASS"
    assert "VERIFIED_PASS" in result.status_summary


# =========================================================================
# 2. Syntax Failure Followed by Successful Repair
# =========================================================================

def test_syntax_failure_followed_by_successful_repair():
    """Initial code has syntax error; Developer repairs on attempt 1."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{SYNTAX_ERROR_CODE}\n```",       # Initial: invalid syntax
            f"```python\n{VALID_GAME_CODE}\n```",          # Repair 1: valid code
        ]
    )
    mock_executor = MockExecutor(simulated_status="PASS")
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=mock_executor,
        task_runner=mock_runner,
    )

    result = orchestrator.run("Asteroids game")

    assert result.success is True
    assert result.repair_attempts == 1
    assert result.validation_result.is_valid is True
    assert mock_runner.dev_call_count == 2
    assert len(result.repair_history) == 1
    assert result.repair_history[0]["phase"] == "static_validation"


# =========================================================================
# 3. Execution Failure Followed by Successful Repair
# =========================================================================

def test_execution_failure_followed_by_successful_repair():
    """Code passes AST validation but fails in executor; repairs on attempt 1."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{VALID_GAME_CODE}\n```",          # Initial valid code
            f"```python\n{VALID_GAME_CODE}\n```",          # Repaired valid code
        ]
    )
    seq_executor = SequentialMockExecutor([
        ExecutionResult(status="FAIL", returncode=1, stderr="ZeroDivisionError: division by zero"),
        ExecutionResult(status="PASS", returncode=0, frames_rendered=60),
    ])
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=seq_executor,
        task_runner=mock_runner,
    )

    result = orchestrator.run("Space Invaders")

    assert result.success is True
    assert result.repair_attempts == 1
    assert result.execution_result.status == "PASS"
    assert mock_runner.dev_call_count == 2
    assert len(result.repair_history) == 1
    assert result.repair_history[0]["phase"] == "runtime_execution"
    assert "ZeroDivisionError" in result.repair_history[0]["stderr"]


def test_execution_timeout_followed_by_successful_repair():
    """Code passes AST check but hangs in executor; repaired on attempt 1."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{VALID_GAME_CODE}\n```",          # Initial valid code that hangs
            f"```python\n{VALID_GAME_CODE}\n```",          # Fixed valid code
        ]
    )
    seq_executor = SequentialMockExecutor([
        ExecutionResult(status="TIMEOUT", returncode=-1, notes="Execution timed out after 10.0s."),
        ExecutionResult(status="PASS", returncode=0, frames_rendered=60),
    ])
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=seq_executor,
        task_runner=mock_runner,
    )

    result = orchestrator.run("Dungeon Crawler")

    assert result.success is True
    assert result.repair_attempts == 1
    assert result.execution_result.status == "PASS"
    assert result.repair_history[0]["phase"] == "runtime_execution"
    assert result.repair_history[0]["status"] == "TIMEOUT"


# =========================================================================
# 4. Failure After Two Unsuccessful Repair Attempts & Retry Limit Enforcement
# =========================================================================

def test_failure_after_two_unsuccessful_static_repairs():
    """Developer fails to produce valid code twice; loop terminates at max 2 repairs."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{SYNTAX_ERROR_CODE}\n```",        # Initial
            f"```python\n{SYNTAX_ERROR_CODE}\n```",        # Repair 1
            f"```python\n{SYNTAX_ERROR_CODE}\n```",        # Repair 2
            f"```python\n{VALID_GAME_CODE}\n```",          # Should NEVER be called
        ]
    )
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key", max_repair_attempts=2),
        executor=MockExecutor(simulated_status="PASS"),
        task_runner=mock_runner,
    )

    result = orchestrator.run("Snake game")

    assert result.success is False
    assert result.repair_attempts == 2
    assert result.max_repair_attempts == 2
    assert result.validation_result.is_valid is False
    assert result.execution_result.status == "FAIL"
    assert "Repairs exhausted" in result.execution_result.notes
    assert mock_runner.dev_call_count == 3  # 1 initial + 2 repairs (NEVER 4)


def test_failure_after_two_unsuccessful_execution_repairs():
    """Code is valid syntax, but executor continuously fails; stops after 2 repairs."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{VALID_GAME_CODE}\n```",          # Initial
            f"```python\n{VALID_GAME_CODE}\n```",          # Repair 1
            f"```python\n{VALID_GAME_CODE}\n```",          # Repair 2
        ]
    )
    always_fail_executor = MockExecutor(
        simulated_status="FAIL",
        simulated_stderr="PygameDisplayError: No display driver found",
        simulated_returncode=1,
    )
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key", max_repair_attempts=2),
        executor=always_fail_executor,
        task_runner=mock_runner,
    )

    result = orchestrator.run("Flappy Bird")

    assert result.success is False
    assert result.repair_attempts == 2
    assert result.execution_result.status == "FAIL"
    assert "FAILED: Pipeline failed after 2/2 repair attempts" in result.status_summary
    assert mock_runner.dev_call_count == 3  # 1 initial + 2 repairs


# =========================================================================
# 5. Missing API Credentials Test
# =========================================================================

def test_missing_api_credentials_raises_value_error():
    """Verify create_llm raises informative ValueError if GEMINI_API_KEY is empty."""
    empty_settings = Settings(gemini_api_key="")
    with pytest.raises(ValueError, match="GEMINI_API_KEY is not configured"):
        create_llm(settings=empty_settings)


# =========================================================================
# 6. QA Report Accuracy and Status Distinctions (PASS, FAIL, NOT_TESTED)
# =========================================================================

def test_qa_task_receives_accurate_empirical_status_not_tested():
    """Verify QA task prompt accurately specifies NOT_TESTED when Docker is missing."""
    mock_runner = MockTaskRunner(developer_responses=[f"```python\n{VALID_GAME_CODE}\n```"])
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=DockerExecutor(),
        task_runner=mock_runner,
    )

    orchestrator.run("Breakout game")

    # Find the QA task passed to the runner
    qa_task = mock_runner.tasks_received[-1]
    assert "Runtime Isolation Status: NOT_TESTED" in qa_task.description
    assert "Static AST Validation: PASSED" in qa_task.description
    assert "DO NOT hallucinate execution success" in qa_task.description


def test_qa_task_receives_accurate_empirical_status_pass():
    """Verify QA task prompt accurately specifies PASS when execution succeeded."""
    mock_runner = MockTaskRunner(developer_responses=[f"```python\n{VALID_GAME_CODE}\n```"])
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=MockExecutor(simulated_status="PASS"),
        task_runner=mock_runner,
    )

    orchestrator.run("Maze game")

    qa_task = mock_runner.tasks_received[-1]
    assert "Runtime Isolation Status: PASS" in qa_task.description


def test_qa_task_receives_accurate_empirical_status_fail():
    """Verify QA task prompt accurately specifies FAIL when code failed validation."""
    mock_runner = MockTaskRunner(
        developer_responses=[
            f"```python\n{SYNTAX_ERROR_CODE}\n```",
            f"```python\n{SYNTAX_ERROR_CODE}\n```",
            f"```python\n{SYNTAX_ERROR_CODE}\n```",
        ]
    )
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=MockExecutor(simulated_status="PASS"),
        task_runner=mock_runner,
    )

    orchestrator.run("Puzzle game")

    qa_task = mock_runner.tasks_received[-1]
    assert "Static AST Validation: FAILED" in qa_task.description


def test_studio_result_serialization():
    """Verify StudioResult.to_dict formats all empirical metrics accurately."""
    mock_runner = MockTaskRunner(developer_responses=[f"```python\n{VALID_GAME_CODE}\n```"])
    orchestrator = StudioOrchestrator(
        settings=Settings(gemini_api_key="test-key"),
        executor=DockerExecutor(),
        task_runner=mock_runner,
    )

    result = orchestrator.run("Racing game")
    d = result.to_dict()

    assert d["success"] is True
    assert d["pipeline_status"] == "COMPLETED"
    assert d["static_validation_status"] == "PASSED"
    assert d["runtime_execution_status"] == "NOT_TESTED"
    assert d["game_verified"] is False
    assert d["repair_attempts"] == 0
    assert d["static_validation"]["is_valid"] is True
    assert d["static_validation"]["has_dual_runtime"] is True
    assert d["static_validation"]["has_smoke_test_hook"] is True
    assert d["runtime_execution"]["status"] == "NOT_TESTED"
    assert d["runtime_execution"]["isolation_backend"] == "none"
    assert "Docker is not available" in d["runtime_execution"]["notes"]
