"""
CrewAI Task definitions for Agentic Game Studio.
"""

from typing import Any, List, Optional


class _FallbackTask:
    def __init__(
        self,
        description: str,
        expected_output: str,
        agent: Any,
        context: Optional[List[Any]] = None,
    ):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent
        self.context = context or []


def create_design_task(designer_agent: Any, game_idea: str) -> Any:
    """Create the Game Design Task."""
    description = f"""
Take the user's game concept: '{game_idea}'
1. Expand it into a cohesive, fun 2D single-screen or endless game.
2. Define the objective, controls, scoring system, and clear win/loss conditions.
3. Specify all game entities (player dimensions, speed, enemies/hazards, collectibles).
4. Keep the scope strictly feasible for a self-contained Pygame implementation.

Output Format:
## Game Design Document
- **Title**: [Game Title]
- **Genre**: [Genre]
- **Core Loop**: [Description of main interaction loop]
- **Controls**: [Exact keys e.g. Space to jump, Arrow keys to move]
- **Entities & Visuals**: [Player, obstacles, colors, dimensions]
- **Scoring & Win/Loss**: [How score accumulates, game over trigger]
- **Technical Acceptance Criteria**: [FPS, screen size, standalone requirements]
"""
    try:
        from crewai import Task
        return Task(
            description=description,
            expected_output="A structured markdown Game Design Document.",
            agent=designer_agent,
        )
    except ImportError:
        return _FallbackTask(
            description=description,
            expected_output="A structured markdown Game Design Document.",
            agent=designer_agent,
        )


def create_developer_task(developer_agent: Any, design_context_task: Any = None) -> Any:
    """Create the initial Game Code Implementation Task."""
    description = """
Using the provided Game Design Document:
Write a COMPLETE, production-quality, standalone Python script using Pygame.

CRITICAL ARCHITECTURAL REQUIREMENTS:
1. Dual-Runtime WebAssembly & Local Compatibility:
   - Import `asyncio`, `pygame`, `sys`, `os`, `random`.
   - Implement the core game loop inside `async def main():`.
   - Call `await asyncio.sleep(0)` on every frame inside the main loop.
   - Use `if __name__ == '__main__': asyncio.run(main())` for local execution.

2. Deterministic Smoke-Test Hook:
   - Check `smoke_test = os.getenv("SMOKE_TEST") == "1" or "--smoke-test" in sys.argv`.
   - Maintain a frame counter: `if smoke_test and frames >= int(os.getenv("SMOKE_TEST_FRAMES", "60")): running = False`.
   - Ensure clean exit with `pygame.quit()` and `return 0` / exit code 0 when smoke testing finishes.

3. Complete Implementation:
   - Handle all events (`pygame.QUIT`, keyboard input).
   - Draw geometry/sprites with clean colors (do NOT load external image files; draw with pygame primitives).
   - Render HUD with score and game-over state.

Output: Provide ONLY the complete, executable Python code enclosed in a ```python ... ``` block.
"""
    context = [design_context_task] if design_context_task else []
    try:
        from crewai import Task
        return Task(
            description=description,
            expected_output="A complete, self-contained, dual-runtime Pygame script.",
            agent=developer_agent,
            context=context,
        )
    except ImportError:
        return _FallbackTask(
            description=description,
            expected_output="A complete, self-contained, dual-runtime Pygame script.",
            agent=developer_agent,
            context=context,
        )


def create_repair_task(
    developer_agent: Any,
    current_code: str,
    failure_feedback: str,
    attempt_number: int,
    max_attempts: int = 2,
) -> Any:
    """Create a targeted Self-Repair Task with empirical error feedback."""
    description = f"""
SELF-REPAIR REQUEST (Attempt {attempt_number} of {max_attempts}):

The previously generated Python code failed validation or execution.
Analyze the exact error feedback below and provide a corrected, complete Python script.

ERROR FEEDBACK & TRACEBACK:
--------------------------------------------------
{failure_feedback}
--------------------------------------------------

PREVIOUS CODE:
--------------------------------------------------
{current_code}
--------------------------------------------------

REPAIR INSTRUCTIONS:
1. Fix the root cause identified in the traceback/validation report.
2. Preserve all dual-runtime requirements (`async def main():`, `await asyncio.sleep(0)`, `asyncio.run(main())`).
3. Ensure the deterministic smoke-test hook (`os.getenv("SMOKE_TEST") == "1"`) remains intact.
4. Output ONLY the complete, corrected Python script in a ```python ... ``` block.
"""
    try:
        from crewai import Task
        return Task(
            description=description,
            expected_output="A corrected, standalone Python script addressing all errors.",
            agent=developer_agent,
        )
    except ImportError:
        return _FallbackTask(
            description=description,
            expected_output="A corrected, standalone Python script addressing all errors.",
            agent=developer_agent,
        )


def create_qa_review_task(
    qa_agent: Any,
    design_spec: str,
    source_code: str,
    validation_summary: str,
    execution_status: str,
    execution_notes: str,
) -> Any:
    """Create the Evidence-Grounded QA Review Task."""
    description = f"""
Audit the following game project against design criteria and empirical validation results.
DO NOT hallucinate execution success. Base your review strictly on the provided facts.

EMPIRICAL TEST STATUS:
- Static AST Validation: {validation_summary}
- Runtime Isolation Status: {execution_status}
- Runtime Isolation Notes: {execution_notes}

GAME SPECIFICATION:
{design_spec}

SOURCE CODE TO AUDIT:
```python
{source_code}
```

AUDIT INSTRUCTIONS:
1. Evaluate feature completeness against the design specification.
2. Verify code quality, structure, and event handling.
3. Summarize empirical test results accurately:
   - If execution was NOT_TESTED (e.g. Docker unavailable), explicitly declare runtime behavior as unverified on the host.
4. Output a structured Quality Assurance Report.
"""
    try:
        from crewai import Task
        return Task(
            description=description,
            expected_output="An evidence-based Quality Assurance Audit Report.",
            agent=qa_agent,
        )
    except ImportError:
        return _FallbackTask(
            description=description,
            expected_output="An evidence-based Quality Assurance Audit Report.",
            agent=qa_agent,
        )
