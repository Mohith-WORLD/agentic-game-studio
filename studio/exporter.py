"""
Artifact Exporter for Agentic Game Studio.
Saves game source code, design documents, README, structured QA JSON report,
and execution logs to isolated run directories.
"""

from datetime import datetime
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, Optional

from sandbox.executor import BaseExecutor, DockerExecutor
from sandbox.validator import validate_python_code
from studio.orchestrator import StudioResult


def _sanitize_slug(text: str, max_words: int = 4) -> str:
    """Generate a clean filesystem slug from a prompt string."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", text).strip().lower()
    words = clean.split()[:max_words]
    return "_".join(words) if words else "game"


def export_artifacts(
    result: StudioResult,
    game_prompt: str,
    base_dir: str = "artifacts",
    run_id: Optional[str] = None,
) -> Path:
    """
    Export all outputs of a Studio run to a unique directory.
    
    Files generated:
    - game.py: Extracted Python game script
    - design.md: Game design specification document
    - README.md: Usage instructions, controls, and empirical status
    - qa_report.json: Structured JSON metrics, validation, repair history, and QA report
    - execution.log: Chronological execution notes, compiler traces, and runtime logs
    """
    timestamp = datetime.now()
    if not run_id:
        slug = _sanitize_slug(game_prompt)
        time_str = timestamp.strftime("%Y%m%d_%H%M%S")
        run_id = f"run_{time_str}_{slug}"

    target_dir = Path(base_dir) / run_id
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. game.py
    code_content = result.source_code.strip()
    if not code_content:
        code_content = "# No game source code was successfully generated during this run.\n"
    elif not code_content.endswith("\n"):
        code_content += "\n"
    (target_dir / "game.py").write_text(code_content, encoding="utf-8")

    # 2. design.md
    design_content = result.game_design.strip()
    if not design_content:
        design_content = f"# Game Design Specification\n\nPrompt: {game_prompt}\n\n*Specification generation did not complete.*\n"
    (target_dir / "design.md").write_text(design_content + "\n", encoding="utf-8")

    # 3. README.md
    readme_content = _generate_readme(result, game_prompt, run_id)
    (target_dir / "README.md").write_text(readme_content, encoding="utf-8")

    # 4. qa_report.json
    qa_data: Dict[str, Any] = {
        "run_id": run_id,
        "prompt": game_prompt,
        "timestamp": timestamp.isoformat(),
        "pipeline_status": result.pipeline_status,
        "static_validation_status": result.static_validation_status,
        "artifact_export_status": "SUCCESS",
        "runtime_execution_status": result.runtime_execution_status,
        "game_verified": result.game_verified,
        "success": result.success,
        "status_summary": result.status_summary,
        "repair_attempts": result.repair_attempts,
        "max_repair_attempts": result.max_repair_attempts,
        "static_validation": {
            "is_valid": result.validation_result.is_valid,
            "syntax_valid": result.validation_result.syntax_valid,
            "structure_valid": result.validation_result.structure_valid,
            "has_dual_runtime": result.validation_result.has_dual_runtime,
            "has_smoke_test_hook": result.validation_result.has_smoke_test_hook,
            "errors": result.validation_result.errors,
            "warnings": result.validation_result.warnings,
        },
        "runtime_execution": {
            "status": result.execution_result.status,
            "isolation_backend": result.execution_result.isolation_backend,
            "returncode": result.execution_result.returncode,
            "stdout": result.execution_result.stdout,
            "stderr": result.execution_result.stderr,
            "frames_rendered": result.execution_result.frames_rendered,
            "notes": result.execution_result.notes,
        },
        "repair_history": result.repair_history,
        "qa_audit_report": result.qa_report,
    }
    with open(target_dir / "qa_report.json", "w", encoding="utf-8") as f:
        json.dump(qa_data, f, indent=2)

    # 5. execution.log
    log_content = _generate_execution_log(result, game_prompt, run_id, timestamp)
    (target_dir / "execution.log").write_text(log_content, encoding="utf-8")

    return target_dir


def _generate_readme(result: StudioResult, game_prompt: str, run_id: str) -> str:
    """Construct an honest, comprehensive README for the generated artifact."""
    val = result.validation_result
    exc = result.execution_result

    val_badge = result.static_validation_status
    exec_badge = result.runtime_execution_status
    pipeline_badge = result.pipeline_status
    verified_badge = "VERIFIED (PASS)" if result.game_verified else "UNVERIFIED"

    return f"""# Generated Game Project: {run_id}

> **Concept**: {game_prompt}

## Empirical Quality & Safety Status

| Verification Gate | Result | Notes |
|---|---|---|
| **Pipeline Status** | `{pipeline_badge}` | Overall workflow completion |
| **Static AST Syntax** | `{val_badge}` | Dual-runtime: `{val.has_dual_runtime}`, Smoke-hook: `{val.has_smoke_test_hook}` |
| **Runtime Isolation** | `{exec_badge}` | Backend: `{exc.isolation_backend}`, Returncode: `{exc.returncode}` |
| **Game Verified** | `{verified_badge}` | {'Verified in isolated runtime.' if result.game_verified else 'NOT verified in isolated runtime.'} |
| **Self-Repair Attempts** | `{result.repair_attempts}/{result.max_repair_attempts}` | History: {len(result.repair_history)} correction cycle(s) |

> [!NOTE]
> When Runtime Isolation is `NOT_TESTED`, execution inside an isolated container was unavailable on the build host.
> In accordance with safety policies, arbitrary AI-generated code was **NOT** executed directly on the host machine.

---

## Prerequisites & Installation

To play this game locally, install Pygame in your environment:

```bash
pip install pygame
```

---

## How to Run the Game

### 1. Interactive Play (Local GUI)
```bash
python game.py
```

### 2. Deterministic Headless Smoke Test
The game features a built-in smoke-test hook that runs for a configured number of frames and cleanly exits with status code `0`:

**Windows PowerShell:**
```powershell
$env:SMOKE_TEST="1"; python game.py
```

**Linux / macOS:**
```bash
SMOKE_TEST=1 python game.py
```

---

## Dual-Runtime WebAssembly Architecture

This game implements the dual-runtime async architecture:
- Core game loop is defined within `async def main():` with `await asyncio.sleep(0)` on every frame.
- Compatible with desktop Python via `asyncio.run(main())`.
- Ready for zero-install browser deployment via Pygbag/WebAssembly.

---

## Artifact Inventory

- `game.py`: Complete Python source code.
- `design.md`: Full game design specification and entity models.
- `qa_report.json`: Structured validation and empirical test metrics.
- `execution.log`: Compiler diagnostic logs, traceback records, and executor notes.
"""


def _generate_execution_log(
    result: StudioResult,
    game_prompt: str,
    run_id: str,
    timestamp: datetime,
) -> str:
    """Format chronological diagnostic execution log."""
    lines = [
        "=" * 70,
        f"AGENTIC GAME STUDIO EXECUTION LOG - {run_id}",
        f"Timestamp : {timestamp.isoformat()}",
        f"Prompt    : {game_prompt}",
        "=" * 70,
        "",
        "--- [PHASE 1: DESIGN SPECIFICATION] ---",
        "Design specification generated successfully." if result.game_design else "Design specification failed or empty.",
        "",
        "--- [PHASE 2: STATIC VALIDATION GATE] ---",
        f"Syntax Valid        : {result.validation_result.syntax_valid}",
        f"Structure Valid     : {result.validation_result.structure_valid}",
        f"Dual-Runtime Loop   : {result.validation_result.has_dual_runtime}",
        f"Smoke-Test Hook     : {result.validation_result.has_smoke_test_hook}",
    ]

    if result.validation_result.errors:
        lines.append(f"Validation Errors   : {'; '.join(result.validation_result.errors)}")
    if result.validation_result.warnings:
        lines.append(f"Validation Warnings : {'; '.join(result.validation_result.warnings)}")

    lines.extend([
        "",
        "--- [PHASE 3: SELF-REPAIR CYCLES] ---",
        f"Total Repair Cycles : {result.repair_attempts} (Max allowed: {result.max_repair_attempts})",
    ])

    if result.repair_history:
        for idx, rec in enumerate(result.repair_history, start=1):
            lines.append(f"  Attempt {rec.get('attempt', idx)} [{rec.get('phase', 'unknown')}]:")
            for k, v in rec.items():
                if k not in ("attempt", "phase"):
                    lines.append(f"    - {k}: {v}")
    else:
        lines.append("  Zero repairs needed. Initial generation satisfied requirements.")

    lines.extend([
        "",
        "--- [PHASE 4: RUNTIME ISOLATION GATE] ---",
        f"Isolation Backend   : {result.execution_result.isolation_backend}",
        f"Execution Status    : {result.execution_result.status}",
        f"Return Code         : {result.execution_result.returncode}",
        f"Frames Rendered     : {result.execution_result.frames_rendered}",
        f"Notes               : {result.execution_result.notes}",
    ])

    if result.execution_result.stdout:
        lines.extend(["", "Executor Stdout:", result.execution_result.stdout])
    if result.execution_result.stderr:
        lines.extend(["", "Executor Stderr:", result.execution_result.stderr])

    lines.extend([
        "",
        "--- [FINAL OUTCOME] ---",
        f"Success             : {result.success}",
        f"Summary             : {result.status_summary}",
        "=" * 70,
    ])

    return "\n".join(lines) + "\n"


def verify_and_reexport_artifact(
    run_dir: Any,
    executor: Optional[Any] = None,
    smoke_frames: int = 60,
    timeout_seconds: int = 15,
) -> Path:
    """
    Reproducibly re-verifies an existing run artifact using an isolated executor,
    and updates qa_report.json, execution.log, and README.md directly from
    the genuine ExecutionResult and ValidationResult evidence.
    """
    run_path = Path(run_dir).resolve()
    game_file = run_path / "game.py"
    if not game_file.exists():
        raise FileNotFoundError(f"Cannot verify artifact: {game_file} does not exist.")

    code = game_file.read_text(encoding="utf-8")
    design_file = run_path / "design.md"
    design_content = design_file.read_text(encoding="utf-8") if design_file.exists() else ""

    qa_json = run_path / "qa_report.json"
    qa_data = {}
    if qa_json.exists():
        try:
            with open(qa_json, "r", encoding="utf-8") as f:
                qa_data = json.load(f)
        except Exception:
            qa_data = {}

    game_prompt = qa_data.get("prompt", "Generated Game")
    run_id = qa_data.get("run_id", run_path.name)
    existing_repairs = qa_data.get("repair_attempts", 0)
    max_repairs = qa_data.get("max_repair_attempts", 2)
    repair_history = qa_data.get("repair_history", [])
    qa_audit_report = qa_data.get("qa_audit_report", "")

    # 1. Deterministic Static Validation
    val_result = validate_python_code(code)

    # 2. Real Execution Boundary
    active_executor = executor or DockerExecutor()
    exec_result = active_executor.run(
        code=code,
        smoke_frames=smoke_frames,
        timeout_seconds=timeout_seconds,
    )

    success = val_result.is_valid and exec_result.status in ("PASS", "NOT_TESTED")
    if success and exec_result.status == "PASS":
        status_summary = (
            f"VERIFIED: Code passed deterministic static AST validation and executed "
            f"cleanly for {exec_result.frames_rendered} frames inside the isolated {exec_result.isolation_backend} sandbox."
        )
    elif success and exec_result.status == "NOT_TESTED":
        status_summary = (
            "STATICALLY_VALID_EXECUTION_UNTESTED: Code passed deterministic static AST checks, "
            "but runtime execution was NOT_TESTED because Docker isolation is unavailable on this host."
        )
    else:
        status_summary = (
            f"FAILED: Static Valid: {val_result.is_valid}, Execution: {exec_result.status}. "
            f"{exec_result.notes}"
        )

    studio_result = StudioResult(
        success=success,
        game_design=design_content,
        source_code=code,
        validation_result=val_result,
        execution_result=exec_result,
        repair_attempts=existing_repairs,
        max_repair_attempts=max_repairs,
        repair_history=repair_history,
        qa_report=qa_audit_report,
        status_summary=status_summary,
    )

    return export_artifacts(
        result=studio_result,
        game_prompt=game_prompt,
        base_dir=str(run_path.parent),
        run_id=run_id,
    )

