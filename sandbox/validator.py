"""
Deterministic Static Code Extractor and AST Validator for Pygame Code.
"""

import ast
import re
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


@dataclass
class ValidationResult:
    """Summary of deterministic static analysis on generated Python code."""
    is_valid: bool
    syntax_valid: bool
    structure_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    extracted_code: str = ""
    error_line: Optional[int] = None
    has_dual_runtime: bool = False
    has_smoke_test_hook: bool = False
    prohibited_calls: List[str] = field(default_factory=list)

    def format_traceback_for_repair(self) -> str:
        """Format errors into an actionable traceback message for the developer agent."""
        if not self.errors:
            return "No static errors detected."
        
        parts = ["Static Validation Failed:"]
        if self.error_line is not None:
            parts.append(f"Primary error at Line {self.error_line}:")
        for err in self.errors:
            parts.append(f"  - {err}")
        if self.warnings:
            parts.append("Warnings to address:")
            for w in self.warnings:
                parts.append(f"  - {w}")
        return "\n".join(parts)


def extract_python_code(raw_output: str) -> str:
    """
    Extract pure Python code from LLM responses containing markdown code fences
    or surrounding conversational commentary.
    """
    if not raw_output:
        return ""

    # Match code blocks with ```python ... ``` or ``` ... ```
    pattern = r"```(?:python)?\s*\n(.*?)```"
    matches = re.findall(pattern, raw_output, flags=re.DOTALL)

    if matches:
        # If multiple code blocks exist, prioritize the one importing pygame
        for block in matches:
            if "import pygame" in block or "pygame." in block:
                return block.strip()
        # Fallback to the longest block
        longest = max(matches, key=len)
        return longest.strip()

    # If no markdown backticks, strip text before the first import
    lines = raw_output.splitlines()
    code_start_idx = 0
    for idx, line in enumerate(lines):
        if line.strip().startswith(("import ", "from ", "#!")):
            code_start_idx = idx
            break

    return "\n".join(lines[code_start_idx:]).strip()


class CodeSecurityAndStructureVisitor(ast.NodeVisitor):
    """AST Visitor to analyze Pygame structure, dual-runtime compatibility, and prohibited calls."""

    PROHIBITED_MODULES = {"subprocess", "socket", "http", "urllib", "requests"}
    PROHIBITED_CALLS = {"system", "popen", "exec", "eval", "spawn"}

    def __init__(self):
        self.imports: Set[str] = set()
        self.has_async_main: bool = False
        self.has_async_sleep: bool = False
        self.has_asyncio_run: bool = False
        self.has_pygame_init: bool = False
        self.has_smoke_test_hook: bool = False
        self.prohibited_found: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            self.imports.add(alias.name)
            if alias.name in self.PROHIBITED_MODULES:
                self.prohibited_found.append(f"Prohibited import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            self.imports.add(node.module)
            if node.module.split(".")[0] in self.PROHIBITED_MODULES:
                self.prohibited_found.append(f"Prohibited import from: {node.module}")
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        if node.name in ("main", "run", "game_loop"):
            self.has_async_main = True
        self.generic_visit(node)

    def visit_Await(self, node: ast.Await):
        # Look for await asyncio.sleep(...)
        if isinstance(node.value, ast.Call):
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "sleep":
                self.has_async_sleep = True
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        # Check for pygame.init()
        if isinstance(func, ast.Attribute) and func.attr == "init":
            self.has_pygame_init = True

        # Check for asyncio.run(...)
        if isinstance(func, ast.Attribute) and func.attr == "run":
            if isinstance(func.value, ast.Name) and func.value.id == "asyncio":
                self.has_asyncio_run = True

        # Check for prohibited function calls
        if isinstance(func, ast.Name) and func.id in self.PROHIBITED_CALLS:
            self.prohibited_found.append(f"Prohibited built-in call: {func.id}()")
        elif isinstance(func, ast.Attribute) and func.attr in self.PROHIBITED_CALLS:
            self.prohibited_found.append(f"Prohibited method call: {func.attr}()")

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        # Look for common smoke test identifiers
        if "smoke_test" in node.id.lower() or "smoke_frames" in node.id.lower():
            self.has_smoke_test_hook = True
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant):
        if isinstance(node.value, str):
            val_lower = node.value.lower()
            if "smoke_test" in val_lower or "--smoke-test" in val_lower:
                self.has_smoke_test_hook = True
        self.generic_visit(node)


def validate_python_code(raw_or_cleaned_code: str) -> ValidationResult:
    """
    Deterministically validate Python code syntax, Pygame structure,
    and security constraints using Python's AST parser.
    """
    cleaned_code = extract_python_code(raw_or_cleaned_code)
    if not cleaned_code:
        return ValidationResult(
            is_valid=False,
            syntax_valid=False,
            structure_valid=False,
            errors=["No Python code found in response."],
            extracted_code="",
        )

    # Step 1: Deterministic Syntax Parsing
    try:
        tree = ast.parse(cleaned_code)
    except SyntaxError as e:
        error_msg = f"SyntaxError at line {e.lineno}, col {e.offset}: {e.msg}"
        return ValidationResult(
            is_valid=False,
            syntax_valid=False,
            structure_valid=False,
            errors=[error_msg],
            extracted_code=cleaned_code,
            error_line=e.lineno,
        )

    # Step 2: Static Structure and Security Inspection
    visitor = CodeSecurityAndStructureVisitor()
    visitor.visit(tree)

    errors: List[str] = []
    warnings: List[str] = []

    # Security check: Prohibited modules or calls
    if visitor.prohibited_found:
        errors.extend(visitor.prohibited_found)

    # Pygame check
    has_pygame = "pygame" in visitor.imports or any(imp.startswith("pygame") for imp in visitor.imports)
    if not has_pygame:
        errors.append("Code does not import 'pygame'.")

    # Dual-runtime check (async def main with await asyncio.sleep(0) and asyncio.run)
    has_asyncio = "asyncio" in visitor.imports
    has_dual_runtime = (
        has_asyncio and 
        visitor.has_async_main and 
        visitor.has_async_sleep
    )

    if not has_dual_runtime:
        errors.append(
            "Dual-runtime requirement missing: Must define 'async def main():', "
            "import 'asyncio', yield via 'await asyncio.sleep(0)' inside the loop, "
            "and execute with 'if __name__ == \"__main__\": asyncio.run(main())'."
        )

    # Smoke-test hook check
    has_smoke_test_hook = visitor.has_smoke_test_hook
    if not has_smoke_test_hook:
        warnings.append(
            "Deterministic smoke-test hook not explicitly detected. "
            "Game should check os.getenv('SMOKE_TEST') or '--smoke-test' to exit cleanly after specified frames."
        )

    is_structure_valid = len(errors) == 0

    return ValidationResult(
        is_valid=is_structure_valid,
        syntax_valid=True,
        structure_valid=is_structure_valid,
        errors=errors,
        warnings=warnings,
        extracted_code=cleaned_code,
        has_dual_runtime=has_dual_runtime,
        has_smoke_test_hook=has_smoke_test_hook,
        prohibited_calls=visitor.prohibited_found,
    )
