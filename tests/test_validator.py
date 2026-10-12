"""
Unit tests for deterministic code extraction and AST validation.
"""

from sandbox.validator import extract_python_code, validate_python_code


VALID_DUAL_RUNTIME_CODE = '''
import asyncio
import os
import pygame

async def main():
    pygame.init()
    screen = pygame.display.set_mode((640, 480))
    clock = pygame.time.Clock()
    running = True
    frame_count = 0
    smoke_test = os.getenv("SMOKE_TEST") == "1"

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill((0, 0, 0))
        pygame.display.flip()
        clock.tick(60)
        frame_count += 1

        if smoke_test and frame_count >= 60:
            running = False

        await asyncio.sleep(0)

    pygame.quit()

if __name__ == "__main__":
    asyncio.run(main())
'''

SYNTAX_ERROR_CODE = '''
import pygame
import asyncio

async def main()
    pygame.init()
'''

MISSING_DUAL_RUNTIME_CODE = '''
import pygame

pygame.init()
screen = pygame.display.set_mode((640, 480))
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
pygame.quit()
'''

PROHIBITED_SUBPROCESS_CODE = '''
import asyncio
import os
import subprocess
import pygame

async def main():
    subprocess.call(["echo", "bad"])
    await asyncio.sleep(0)
'''


def test_extract_python_code_from_markdown():
    markdown = f"""
Here is your complete game implementation:

```python
{VALID_DUAL_RUNTIME_CODE}
```

Instructions to play:
Press Space to jump.
"""
    extracted = extract_python_code(markdown)
    assert "import asyncio" in extracted
    assert "async def main():" in extracted
    assert "Instructions to play:" not in extracted


def test_validate_valid_code():
    res = validate_python_code(VALID_DUAL_RUNTIME_CODE)
    assert res.is_valid is True
    assert res.syntax_valid is True
    assert res.structure_valid is True
    assert res.has_dual_runtime is True
    assert res.has_smoke_test_hook is True
    assert len(res.errors) == 0


def test_validate_syntax_error():
    res = validate_python_code(SYNTAX_ERROR_CODE)
    assert res.is_valid is False
    assert res.syntax_valid is False
    assert res.error_line == 4
    assert any("SyntaxError" in err for err in res.errors)
    traceback_msg = res.format_traceback_for_repair()
    assert "SyntaxError" in traceback_msg
    assert "Line 4" in traceback_msg


def test_validate_missing_dual_runtime():
    res = validate_python_code(MISSING_DUAL_RUNTIME_CODE)
    assert res.is_valid is False
    assert res.syntax_valid is True
    assert res.has_dual_runtime is False
    assert any("Dual-runtime requirement missing" in err for err in res.errors)


def test_validate_prohibited_module():
    res = validate_python_code(PROHIBITED_SUBPROCESS_CODE)
    assert res.is_valid is False
    assert any("Prohibited import: subprocess" in err for err in res.errors)
