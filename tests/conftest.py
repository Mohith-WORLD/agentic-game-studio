"""
Shared pytest fixtures for Agentic Game Studio test suite.
"""

import pytest

from sandbox.executor import ExecutionResult
from sandbox.validator import ValidationResult
from studio.orchestrator import StudioResult


SAMPLE_SOURCE_CODE = """import asyncio
import os
import pygame

async def main():
    pygame.init()
    smoke_test = os.getenv("SMOKE_TEST") == "1"
    pygame.quit()
    return 0

if __name__ == "__main__":
    asyncio.run(main())
"""

SAMPLE_DESIGN_SPEC = """## Game Design Document
- **Title**: Neon Rush
- **Controls**: Arrow Keys
- **Objective**: Dodge falling obstacles
"""


@pytest.fixture
def dummy_success_result():
    return StudioResult(
        success=True,
        game_design=SAMPLE_DESIGN_SPEC,
        source_code=SAMPLE_SOURCE_CODE,
        validation_result=ValidationResult(
            is_valid=True,
            syntax_valid=True,
            structure_valid=True,
            has_dual_runtime=True,
            has_smoke_test_hook=True,
            errors=[],
            warnings=[],
        ),
        execution_result=ExecutionResult(
            status="NOT_TESTED",
            isolation_backend="none",
            notes="Docker is not available on this host. Reported as NOT_TESTED.",
        ),
        repair_attempts=0,
        max_repair_attempts=2,
        repair_history=[],
        qa_report="## QA Report: Statically verified.",
        status_summary="STATICALLY_VALID_EXECUTION_UNTESTED: Code passed static checks.",
    )


@pytest.fixture
def dummy_failed_result():
    return StudioResult(
        success=False,
        game_design="",
        source_code="",
        validation_result=ValidationResult(
            is_valid=False,
            syntax_valid=False,
            structure_valid=False,
            has_dual_runtime=False,
            has_smoke_test_hook=False,
            errors=["SyntaxError: invalid syntax on line 4"],
            warnings=[],
        ),
        execution_result=ExecutionResult(
            status="FAIL",
            isolation_backend="none",
            notes="Repairs exhausted after 2 attempts.",
        ),
        repair_attempts=2,
        max_repair_attempts=2,
        repair_history=[
            {"attempt": 1, "phase": "static_validation", "error": ["SyntaxError"]},
            {"attempt": 2, "phase": "static_validation", "error": ["SyntaxError"]},
        ],
        qa_report="## QA Report: Failed validation.",
        status_summary="FAILED: Pipeline failed after 2/2 repair attempts.",
    )
