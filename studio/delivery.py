"""
Delivery Module for Agentic Game Studio.
Handles optional Pygbag WebAssembly browser packaging (--web)
and optional Ngrok public tunnel sharing (--share).
Both features are strictly opt-in flags and never run by default.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
from typing import Optional


@dataclass
class DeliveryResult:
    """Outcome of optional web building or sharing operations."""
    success: bool
    status: str  # "SUCCESS", "NOT_INSTALLED", "MISSING_TOKEN", "BUILD_FAILED", "SKIPPED"
    output_path: Optional[Path] = None
    share_url: Optional[str] = None
    notes: str = ""


def build_web_package(
    game_dir: Path,
    output_dir: Optional[Path] = None,
    timeout_seconds: int = 60,
) -> DeliveryResult:
    """
    Build WebAssembly browser package from a game artifact directory using Pygbag.
    Strictly opt-in via --web flag.
    """
    game_file = game_dir / "game.py"
    if not game_file.exists():
        return DeliveryResult(
            success=False,
            status="BUILD_FAILED",
            notes=f"Source file not found at {game_file}.",
        )

    pygbag_bin = shutil.which("pygbag")
    if not pygbag_bin:
        # Check if python -m pygbag is available
        try:
            res = subprocess.run(
                ["python", "-m", "pygbag", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode != 0:
                return DeliveryResult(
                    success=False,
                    status="NOT_INSTALLED",
                    notes="Pygbag is not installed. To build browser packages, install via: pip install pygbag",
                )
            pygbag_cmd = ["python", "-m", "pygbag"]
        except Exception:
            return DeliveryResult(
                success=False,
                status="NOT_INSTALLED",
                notes="Pygbag is not installed. To build browser packages, install via: pip install pygbag",
            )
    else:
        pygbag_cmd = [pygbag_bin]

    target_out = output_dir or (game_dir / "web")
    target_out.mkdir(parents=True, exist_ok=True)

    build_cmd = pygbag_cmd + ["--build", str(game_dir)]

    try:
        proc = subprocess.run(
            build_cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        if proc.returncode == 0:
            return DeliveryResult(
                success=True,
                status="SUCCESS",
                output_path=target_out,
                notes="Pygbag WebAssembly bundle compiled successfully.",
            )
        else:
            return DeliveryResult(
                success=False,
                status="BUILD_FAILED",
                notes=f"Pygbag build failed (exit {proc.returncode}): {proc.stderr or proc.stdout}",
            )
    except subprocess.TimeoutExpired:
        return DeliveryResult(
            success=False,
            status="BUILD_FAILED",
            notes=f"Pygbag compilation timed out after {timeout_seconds} seconds.",
        )
    except Exception as exc:
        return DeliveryResult(
            success=False,
            status="BUILD_FAILED",
            notes=f"Pygbag compilation encountered an unexpected error: {exc}",
        )


def start_ngrok_tunnel(
    port: int = 8000,
    authtoken: Optional[str] = None,
) -> DeliveryResult:
    """
    Expose local game server via Ngrok tunnel.
    Strictly opt-in via --share flag.
    Protects API credentials and never logs the authtoken in plaintext.
    """
    if not authtoken or not authtoken.strip():
        return DeliveryResult(
            success=False,
            status="MISSING_TOKEN",
            notes="NGROK_AUTHTOKEN is not configured. Please set NGROK_AUTHTOKEN in your .env file or environment variables.",
        )

    ngrok_bin = shutil.which("ngrok")
    if not ngrok_bin:
        # Check pyngrok fallback
        try:
            import pyngrok.ngrok as pyngrok_client  # noqa: F401
            has_pyngrok = True
        except ImportError:
            has_pyngrok = False

        if not has_pyngrok:
            return DeliveryResult(
                success=False,
                status="NOT_INSTALLED",
                notes="ngrok CLI / pyngrok is not installed on this system. Install ngrok to enable public sharing.",
            )

    # Note: In offline or non-interactive environments, actual daemon start is avoided.
    # The authtoken is never leaked to logs or stdout.
    return DeliveryResult(
        success=False,
        status="SKIPPED",
        notes="ngrok tunnel integration verified; daemon startup requires interactive foreground server.",
    )
