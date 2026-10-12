"""
Self-Repair Controller and Studio Pipeline Orchestrator.
Enforces deterministic static validation, execution isolation checking,
and a strict maximum limit of two repair attempts using Python control logic.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from config.settings import Settings, load_settings
from sandbox.validator import ValidationResult, extract_python_code, validate_python_code
from sandbox.executor import BaseExecutor, DockerExecutor, ExecutionResult
from studio.agents import create_game_designer, create_game_developer, create_qa_engineer
from studio.tasks import (
    create_design_task,
    create_developer_task,
    create_qa_review_task,
    create_repair_task,
)


@dataclass
class StudioResult:
    """Consolidated outcome of the game generation, validation, and repair pipeline."""
    success: bool
    game_design: str
    source_code: str
    validation_result: ValidationResult
    execution_result: ExecutionResult
    repair_attempts: int
    max_repair_attempts: int
    repair_history: List[Dict[str, Any]] = field(default_factory=list)
    qa_report: str = ""
    status_summary: str = ""

    @property
    def pipeline_status(self) -> str:
        return "COMPLETED" if self.success else "FAILED"

    @property
    def static_validation_status(self) -> str:
        return "PASSED" if self.validation_result.is_valid else "FAILED"

    @property
    def runtime_execution_status(self) -> str:
        return self.execution_result.status

    @property
    def game_verified(self) -> bool:
        """
        True ONLY when both static validation and dynamic execution checks actually passed.
        If runtime execution was NOT_TESTED, FAIL, or TIMEOUT, this is strictly False.
        """
        return self.validation_result.is_valid and self.execution_result.status == "PASS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_status": self.pipeline_status,
            "static_validation_status": self.static_validation_status,
            "runtime_execution_status": self.runtime_execution_status,
            "game_verified": self.game_verified,
            "success": self.success,
            "status_summary": self.status_summary,
            "repair_attempts": self.repair_attempts,
            "max_repair_attempts": self.max_repair_attempts,
            "static_validation": {
                "is_valid": self.validation_result.is_valid,
                "syntax_valid": self.validation_result.syntax_valid,
                "structure_valid": self.validation_result.structure_valid,
                "has_dual_runtime": self.validation_result.has_dual_runtime,
                "has_smoke_test_hook": self.validation_result.has_smoke_test_hook,
                "errors": self.validation_result.errors,
                "warnings": self.validation_result.warnings,
            },
            "runtime_execution": {
                "status": self.execution_result.status,
                "isolation_backend": self.execution_result.isolation_backend,
                "returncode": self.execution_result.returncode,
                "frames_rendered": self.execution_result.frames_rendered,
                "notes": self.execution_result.notes,
            },
            "repair_history": self.repair_history,
            "qa_audit_report": self.qa_report,
        }


class StudioOrchestrator:
    """
    Coordinates multi-agent game generation with closed-loop deterministic repair.
    Strictly caps repair attempts at max_repair_attempts (default: 2).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        executor: Optional[BaseExecutor] = None,
        llm: Any = None,
        task_runner: Optional[Callable[[Any, Any], str]] = None,
    ):
        self.settings = settings or load_settings()
        self.executor = executor or DockerExecutor()
        self.llm = llm
        self.task_runner = task_runner or self._default_task_runner

        # Lazy agent initialization
        self._designer = None
        self._developer = None
        self._qa = None

    def _default_task_runner(self, agent: Any, task: Any) -> str:
        """Run a single task using CrewAI Crew."""
        try:
            from crewai import Crew, Process
            crew = Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=False,
            )
            res = crew.kickoff()
            return str(getattr(res, "raw", res))
        except ImportError:
            raise RuntimeError(
                "CrewAI is not installed. To execute live agents, run 'pip install -r requirements.txt'. "
                "For offline testing, inject a task_runner callable into StudioOrchestrator."
            )

    def get_designer(self) -> Any:
        if self._designer is None:
            self._designer = create_game_designer(llm=self.llm, settings=self.settings)
        return self._designer

    def get_developer(self) -> Any:
        if self._developer is None:
            self._developer = create_game_developer(llm=self.llm, settings=self.settings)
        return self._developer

    def get_qa(self) -> Any:
        if self._qa is None:
            self._qa = create_qa_engineer(llm=self.llm, settings=self.settings)
        return self._qa

    def run(self, game_idea: str) -> StudioResult:
        """
        Execute the full studio workflow:
        1. Design Specification
        2. Initial Code Generation
        3. Static Validation & Dynamic Execution with Max 2 Self-Repairs
        4. Grounded QA Audit
        """
        # --- Stage 1: Game Design Specification ---
        designer = self.get_designer()
        design_task = create_design_task(designer, game_idea)
        design_doc = self.task_runner(designer, design_task)

        # --- Stage 2: Initial Code Generation ---
        developer = self.get_developer()
        dev_task = create_developer_task(developer)
        raw_code = self.task_runner(developer, dev_task)
        current_code = extract_python_code(raw_code)

        # --- Stage 3: Deterministic Validation, Execution & Self-Repair Loop ---
        repair_attempts = 0
        max_repairs = self.settings.max_repair_attempts
        repair_history: List[Dict[str, Any]] = []

        val_result: ValidationResult = validate_python_code(current_code)
        exec_result: ExecutionResult = ExecutionResult(
            status="NOT_TESTED",
            notes="Pending static validation."
        )

        while True:
            # Step A: Deterministic Static Validation Gate
            val_result = validate_python_code(current_code)

            if not val_result.is_valid:
                # Static failure
                failure_reason = "Static AST Validation Failure"
                feedback = val_result.format_traceback_for_repair()
                repair_record = {
                    "attempt": repair_attempts + 1,
                    "phase": "static_validation",
                    "error": val_result.errors,
                    "error_line": val_result.error_line,
                }
                repair_history.append(repair_record)

                if repair_attempts < max_repairs:
                    repair_attempts += 1
                    repair_task = create_repair_task(
                        developer_agent=developer,
                        current_code=current_code,
                        failure_feedback=feedback,
                        attempt_number=repair_attempts,
                        max_attempts=max_repairs,
                    )
                    repaired_raw = self.task_runner(developer, repair_task)
                    current_code = extract_python_code(repaired_raw)
                    continue
                else:
                    # Exceeded retry budget
                    exec_result = ExecutionResult(
                        status="FAIL",
                        notes=f"Repairs exhausted after {repair_attempts} attempts. Code remains statically invalid."
                    )
                    break

            # Step B: Dynamic Execution Isolation Gate (Only reached if static check passes)
            exec_result = self.executor.run(
                code=current_code,
                smoke_frames=self.settings.smoke_test_frames,
                timeout_seconds=self.settings.execution_timeout_seconds,
            )

            if exec_result.status == "NOT_TESTED":
                # Docker is unavailable; fail-closed safety policy prevents host execution
                break

            if exec_result.status in ("FAIL", "TIMEOUT"):
                # Execution failed
                failure_reason = f"Runtime Execution {exec_result.status}"
                feedback = f"Execution Stderr:\n{exec_result.stderr}\n\nNotes: {exec_result.notes}"
                repair_record = {
                    "attempt": repair_attempts + 1,
                    "phase": "runtime_execution",
                    "status": exec_result.status,
                    "stderr": exec_result.stderr,
                }
                repair_history.append(repair_record)

                if repair_attempts < max_repairs:
                    repair_attempts += 1
                    repair_task = create_repair_task(
                        developer_agent=developer,
                        current_code=current_code,
                        failure_feedback=feedback,
                        attempt_number=repair_attempts,
                        max_attempts=max_repairs,
                    )
                    repaired_raw = self.task_runner(developer, repair_task)
                    current_code = extract_python_code(repaired_raw)
                    continue
                else:
                    # Exceeded retry budget
                    break

            if exec_result.status == "PASS":
                # Both static and dynamic checks passed cleanly
                break

        # --- Stage 4: Grounded QA Audit ---
        qa_agent = self.get_qa()
        validation_summary = (
            "PASSED (Syntax valid, Dual-runtime valid, AST verified)"
            if val_result.is_valid
            else f"FAILED ({'; '.join(val_result.errors)})"
        )
        qa_task = create_qa_review_task(
            qa_agent=qa_agent,
            design_spec=design_doc,
            source_code=current_code,
            validation_summary=validation_summary,
            execution_status=exec_result.status,
            execution_notes=exec_result.notes,
        )
        qa_report = self.task_runner(qa_agent, qa_task)

        # Determine overall pipeline success
        repairs_exhausted = (
            (not val_result.is_valid or exec_result.status in ("FAIL", "TIMEOUT"))
            and repair_attempts >= max_repairs
        )
        success = val_result.is_valid and not repairs_exhausted and exec_result.status in ("PASS", "NOT_TESTED")

        if success and exec_result.status == "NOT_TESTED":
            status_summary = (
                "STATICALLY_VALID_EXECUTION_UNTESTED: Code passed deterministic static AST checks, "
                "but runtime execution was NOT_TESTED because Docker isolation is unavailable on this host."
            )
        elif success and exec_result.status == "PASS":
            status_summary = "VERIFIED_PASS: Both static validation and isolated execution passed cleanly."
        else:
            status_summary = (
                f"FAILED: Pipeline failed after {repair_attempts}/{max_repairs} repair attempts. "
                f"Static Valid: {val_result.is_valid}, Execution: {exec_result.status}."
            )

        return StudioResult(
            success=success,
            game_design=design_doc,
            source_code=current_code,
            validation_result=val_result,
            execution_result=exec_result,
            repair_attempts=repair_attempts,
            max_repair_attempts=max_repairs,
            repair_history=repair_history,
            qa_report=qa_report,
            status_summary=status_summary,
        )
