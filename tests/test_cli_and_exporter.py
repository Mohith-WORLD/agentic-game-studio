"""
Offline tests for Artifact Exporter and CLI Entrypoint.
Verifies file generation, schema integrity, CLI validation, and status reporting.
"""

import json
from pathlib import Path
from unittest.mock import patch
import pytest

from config.settings import Settings
from main import create_parser, run_cli
from studio.exporter import export_artifacts


# =========================================================================
# 1. CLI Argument Validation Tests
# =========================================================================

def test_cli_parser_help_and_defaults():
    parser = create_parser()
    args = parser.parse_args(["My Retro Game"])
    assert args.prompt == "My Retro Game"
    assert args.artifacts_dir == "artifacts"
    assert args.max_repairs is None


def test_cli_rejects_empty_prompt(capsys):
    exit_code = run_cli([])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Game prompt cannot be empty" in captured.err


def test_cli_rejects_whitespace_prompt(capsys):
    exit_code = run_cli(["   \t\n  "])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "Game prompt cannot be empty" in captured.err


def test_cli_rejects_max_repairs_greater_than_two(capsys):
    exit_code = run_cli(["Space Odyssey", "--max-repairs", "3"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--max-repairs must be between 0 and 2" in captured.err


def test_cli_rejects_negative_max_repairs(capsys):
    exit_code = run_cli(["Space Odyssey", "--max-repairs", "-1"])
    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--max-repairs must be between 0 and 2" in captured.err


def test_settings_caps_max_repairs_at_two():
    s_high = Settings(max_repair_attempts=5)
    assert s_high.max_repair_attempts == 2

    s_neg = Settings(max_repair_attempts=-3)
    assert s_neg.max_repair_attempts == 0


# =========================================================================
# 2. Missing API Credentials Test
# =========================================================================

def test_cli_handles_missing_api_credentials(capsys, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with patch("main.load_settings", return_value=Settings(gemini_api_key="")):
        exit_code = run_cli(["Space Odyssey"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "GEMINI_API_KEY is not configured" in captured.err


# =========================================================================
# 3. Artifact Directory Creation and Export
# =========================================================================

def test_artifact_export_creates_directory_and_expected_files(tmp_path, dummy_success_result):
    artifacts_base = tmp_path / "artifacts"
    export_dir = export_artifacts(
        result=dummy_success_result,
        game_prompt="Neon Runner",
        base_dir=str(artifacts_base),
        run_id="run_test_001",
    )

    assert export_dir.exists()
    assert (export_dir / "game.py").exists()
    assert (export_dir / "design.md").exists()
    assert (export_dir / "README.md").exists()
    assert (export_dir / "qa_report.json").exists()
    assert (export_dir / "execution.log").exists()

    # Verify game.py content
    code = (export_dir / "game.py").read_text(encoding="utf-8")
    assert "async def main():" in code
    assert "smoke_test" in code

    # Verify design.md content
    design = (export_dir / "design.md").read_text(encoding="utf-8")
    assert "Neon Rush" in design


def test_artifact_export_unique_run_directories(tmp_path, dummy_success_result):
    artifacts_base = tmp_path / "artifacts"
    dir1 = export_artifacts(
        result=dummy_success_result,
        game_prompt="Platformer",
        base_dir=str(artifacts_base),
        run_id="run_platformer_alpha",
    )
    dir2 = export_artifacts(
        result=dummy_success_result,
        game_prompt="Platformer",
        base_dir=str(artifacts_base),
        run_id="run_platformer_beta",
    )

    assert dir1 != dir2
    assert dir1.exists()
    assert dir2.exists()


# =========================================================================
# 4. Incomplete & Failed Generation Handling
# =========================================================================

def test_artifact_export_handles_failed_generation(tmp_path, dummy_failed_result):
    artifacts_base = tmp_path / "artifacts"
    export_dir = export_artifacts(
        result=dummy_failed_result,
        game_prompt="Unreal Physics Game",
        base_dir=str(artifacts_base),
        run_id="run_failed_001",
    )

    assert export_dir.exists()
    code = (export_dir / "game.py").read_text(encoding="utf-8")
    assert "No game source code was successfully generated" in code

    design = (export_dir / "design.md").read_text(encoding="utf-8")
    assert "Specification generation did not complete" in design

    readme = (export_dir / "README.md").read_text(encoding="utf-8")
    assert "FAILED" in readme


# =========================================================================
# 5. JSON Serialization Integrity
# =========================================================================

def test_qa_report_json_schema_and_serialization(tmp_path, dummy_success_result):
    export_dir = export_artifacts(
        result=dummy_success_result,
        game_prompt="Tetris Clone",
        base_dir=str(tmp_path),
        run_id="run_json_test",
    )

    json_path = export_dir / "qa_report.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["run_id"] == "run_json_test"
    assert data["prompt"] == "Tetris Clone"
    assert data["pipeline_status"] == "COMPLETED"
    assert data["static_validation_status"] == "PASSED"
    assert data["artifact_export_status"] == "SUCCESS"
    assert data["runtime_execution_status"] == "NOT_TESTED"
    assert data["game_verified"] is False
    assert data["success"] is True
    assert data["repair_attempts"] == 0
    assert data["max_repair_attempts"] == 2
    assert data["static_validation"]["is_valid"] is True
    assert data["static_validation"]["has_dual_runtime"] is True
    assert data["static_validation"]["has_smoke_test_hook"] is True
    assert data["runtime_execution"]["status"] == "NOT_TESTED"
    assert data["qa_audit_report"] == "## QA Report: Statically verified."


# =========================================================================
# 6. Status Distinction (PASS, FAIL, NOT_TESTED) in Reports
# =========================================================================

def test_status_distinction_not_tested(tmp_path, dummy_success_result):
    dummy_success_result.execution_result.status = "NOT_TESTED"
    export_dir = export_artifacts(
        result=dummy_success_result,
        game_prompt="Dodge",
        base_dir=str(tmp_path),
        run_id="run_not_tested",
    )

    readme = (export_dir / "README.md").read_text(encoding="utf-8")
    assert "`NOT_TESTED`" in readme
    assert "UNVERIFIED" in readme
    with open(export_dir / "qa_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["game_verified"] is False
    assert data["runtime_execution_status"] == "NOT_TESTED"


def test_status_distinction_pass(tmp_path, dummy_success_result):
    dummy_success_result.execution_result.status = "PASS"
    dummy_success_result.execution_result.isolation_backend = "docker"
    dummy_success_result.execution_result.returncode = 0
    export_dir = export_artifacts(
        result=dummy_success_result,
        game_prompt="Dodge",
        base_dir=str(tmp_path),
        run_id="run_pass",
    )

    readme = (export_dir / "README.md").read_text(encoding="utf-8")
    assert "`PASS`" in readme
    assert "VERIFIED (PASS)" in readme
    with open(export_dir / "qa_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["game_verified"] is True
    assert data["runtime_execution_status"] == "PASS"


def test_status_distinction_fail(tmp_path, dummy_failed_result):
    export_dir = export_artifacts(
        result=dummy_failed_result,
        game_prompt="Broken",
        base_dir=str(tmp_path),
        run_id="run_fail",
    )

    readme = (export_dir / "README.md").read_text(encoding="utf-8")
    assert "`FAIL`" in readme
    with open(export_dir / "qa_report.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["game_verified"] is False
    assert data["runtime_execution_status"] == "FAIL"


# =========================================================================
# 7. End-to-End CLI Invocation with Mocked Orchestrator
# =========================================================================

def test_cli_end_to_end_mocked_success(tmp_path, capsys, monkeypatch, dummy_success_result):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")

    with patch("main.StudioOrchestrator.run", return_value=dummy_success_result):
        exit_code = run_cli([
            "Alien Invaders",
            "--artifacts-dir",
            str(tmp_path / "custom_artifacts"),
        ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Pipeline Status            : COMPLETED" in captured.out
    assert "Static AST Validation      : PASSED" in captured.out
    assert "Runtime Isolation Status   : NOT_TESTED" in captured.out
    assert "Game Verified              : NO (Unverified" in captured.out
    assert "Artifacts exported :" in captured.out

    # Check that artifact files actually exist on disk
    exported_dirs = list((tmp_path / "custom_artifacts").glob("run_*"))
    assert len(exported_dirs) == 1
    assert (exported_dirs[0] / "game.py").exists()
    assert (exported_dirs[0] / "qa_report.json").exists()
