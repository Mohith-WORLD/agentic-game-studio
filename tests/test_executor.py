"""
Unit tests for the execution sandbox interface and isolation boundaries.
"""

from sandbox.executor import DockerExecutor, MockExecutor


def test_docker_executor_reports_not_tested_when_docker_unavailable(monkeypatch):
    monkeypatch.setattr(DockerExecutor, "is_docker_available", staticmethod(lambda: False))
    executor = DockerExecutor()
    assert executor.is_docker_available() is False

    result = executor.run(
        code="print('Hello from game')",
        smoke_frames=60,
        timeout_seconds=10,
    )

    assert result.status == "NOT_TESTED"
    assert result.was_tested is False
    assert result.passed is False
    assert result.isolation_backend == "none"
    assert "Docker is not available" in result.notes
    assert "NOT_TESTED" in result.notes


def test_mock_executor_pass_simulation():
    mock = MockExecutor(
        simulated_status="PASS",
        simulated_stdout="Game initialized and rendered 60 frames.",
        frames=60,
    )
    result = mock.run(code="mock_code", smoke_frames=60)
    assert result.status == "PASS"
    assert result.passed is True
    assert result.was_tested is True
    assert result.frames_rendered == 60
    assert result.isolation_backend == "mock"


def test_mock_executor_fail_simulation():
    mock = MockExecutor(
        simulated_status="FAIL",
        simulated_stderr="pygame.error: display Surface quit unexpectedly",
        simulated_returncode=1,
    )
    result = mock.run(code="mock_code")
    assert result.status == "FAIL"
    assert result.passed is False
    assert result.was_tested is True
    assert "display Surface quit" in result.stderr
