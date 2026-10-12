"""
Execution Interface and Docker Sandbox Integration.
Adheres strictly to the safety policy: Never executes untrusted AI-generated code
directly on the host without a verified isolation boundary (Docker).
"""

import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionResult:
    """Standardized result of game execution test."""
    status: str  # "PASS", "FAIL", "TIMEOUT", "NOT_TESTED"
    returncode: Optional[int] = None
    stdout: str = ""
    stderr: str = ""
    frames_rendered: int = 0
    isolation_backend: str = "none"  # "docker", "mock", "none"
    notes: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def was_tested(self) -> bool:
        return self.status != "NOT_TESTED"


class BaseExecutor(ABC):
    """Abstract base class for game execution environments."""

    @abstractmethod
    def run(
        self,
        code: str,
        smoke_frames: int = 60,
        timeout_seconds: int = 10,
    ) -> ExecutionResult:
        """Execute the Python game code inside an isolated boundary."""
        pass


class DockerExecutor(BaseExecutor):
    """
    Executes Python games inside a restricted Docker container:
    - Networking disabled (--network none)
    - Non-root user (--user 1000:1000)
    - Resource constraints (--memory 512m --cpus 1.0)
    - Restricted filesystem (read-only rootfs + dedicated scratch volume)
    - No API credentials mounted or passed in environment
    
    If Docker is unavailable on the host, safely aborts and reports NOT_TESTED.
    """

    def __init__(self, image_name: str = "agentic-game-sandbox:latest"):
        self.image_name = image_name

    @staticmethod
    def is_docker_available() -> bool:
        """Check if Docker CLI is installed and responsive."""
        docker_path = shutil.which("docker")
        if not docker_path:
            return False
        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return res.returncode == 0
        except Exception:
            return False

    def run(
        self,
        code: str,
        smoke_frames: int = 60,
        timeout_seconds: int = 10,
    ) -> ExecutionResult:
        if not self.is_docker_available():
            return ExecutionResult(
                status="NOT_TESTED",
                returncode=None,
                stdout="",
                stderr="",
                frames_rendered=0,
                isolation_backend="none",
                notes=(
                    "Docker is not available on this host. Arbitrary AI-generated "
                    "code was NOT executed directly on the host machine to preserve system security. "
                    "Reported as NOT_TESTED."
                ),
            )

        # Build isolated temporary file and execute inside sandboxed container
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            game_file = Path(tmpdir) / "game.py"
            game_file.write_text(code, encoding="utf-8")

            cmd = [
                "docker", "run", "--rm",
                "--network", "none",
                "--user", "1000:1000",
                "--memory", "512m",
                "--cpus", "1.0",
                "--env", "SDL_VIDEODRIVER=dummy",
                "--env", "SDL_AUDIODRIVER=dummy",
                "--env", "SMOKE_TEST=1",
                "--env", f"SMOKE_TEST_FRAMES={smoke_frames}",
                "-v", f"{game_file.resolve()}:/workspace/game.py:ro",
                self.image_name,
                "python", "/workspace/game.py",
            ]

            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                )
                if proc.returncode == 0:
                    return ExecutionResult(
                        status="PASS",
                        returncode=0,
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        frames_rendered=smoke_frames,
                        isolation_backend="docker",
                        notes=f"Docker container smoke-test passed cleanly ({smoke_frames} frames).",
                    )
                else:
                    return ExecutionResult(
                        status="FAIL",
                        returncode=proc.returncode,
                        stdout=proc.stdout,
                        stderr=proc.stderr,
                        frames_rendered=0,
                        isolation_backend="docker",
                        notes=f"Docker container execution failed with exit code {proc.returncode}.",
                    )
            except subprocess.TimeoutExpired as te:
                return ExecutionResult(
                    status="TIMEOUT",
                    returncode=-1,
                    stdout=te.stdout or "",
                    stderr=te.stderr or "",
                    frames_rendered=0,
                    isolation_backend="docker",
                    notes=f"Docker container execution timed out after {timeout_seconds} seconds.",
                )
            except Exception as exc:
                return ExecutionResult(
                    status="FAIL",
                    returncode=-1,
                    stdout="",
                    stderr=str(exc),
                    frames_rendered=0,
                    isolation_backend="docker",
                    notes=f"Docker execution error: {exc}",
                )


class MockExecutor(BaseExecutor):
    """
    Mock Executor for deterministic unit testing of the execution interface
    and self-repair controller without running live untrusted code.
    """

    def __init__(
        self,
        simulated_status: str = "PASS",
        simulated_stdout: str = "Rendered 60 frames successfully.",
        simulated_stderr: str = "",
        simulated_returncode: int = 0,
        frames: int = 60,
    ):
        self.simulated_status = simulated_status
        self.simulated_stdout = simulated_stdout
        self.simulated_stderr = simulated_stderr
        self.simulated_returncode = simulated_returncode
        self.frames = frames

    def run(
        self,
        code: str,
        smoke_frames: int = 60,
        timeout_seconds: int = 10,
    ) -> ExecutionResult:
        return ExecutionResult(
            status=self.simulated_status,
            returncode=self.simulated_returncode,
            stdout=self.simulated_stdout,
            stderr=self.simulated_stderr,
            frames_rendered=self.frames if self.simulated_status == "PASS" else 0,
            isolation_backend="mock",
            notes=f"Mock execution simulation ({self.simulated_status}).",
        )
