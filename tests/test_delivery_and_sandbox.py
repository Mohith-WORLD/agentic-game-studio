"""
Unit and integration tests for Stage 7:
Isolated Docker sandbox configuration and Delivery (Pygbag / Ngrok).
"""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch
import pytest

from sandbox.executor import DockerExecutor, ExecutionResult
from studio.delivery import build_web_package, start_ngrok_tunnel
from main import run_cli


# =========================================================================
# 1. Dockerfile Security Configuration Tests
# =========================================================================

def test_dockerfile_exists_and_enforces_security_constraints():
    """Verify Dockerfile enforces non-root execution and dummy SDL drivers."""
    dockerfile_path = Path("Dockerfile")
    assert dockerfile_path.exists(), "Dockerfile must exist at the project root."

    content = dockerfile_path.read_text(encoding="utf-8")
    assert "useradd -u 1000" in content, "Must configure non-root user (uid 1000)."
    assert "USER sandbox" in content, "Must switch to non-root user."
    assert "SDL_VIDEODRIVER=dummy" in content, "Must configure headless dummy video driver."
    assert "SDL_AUDIODRIVER=dummy" in content, "Must configure headless dummy audio driver."
    assert "pygame" in content, "Must install Pygame in the sandbox image."


# =========================================================================
# 2. DockerExecutor Security Flags and Isolation Tests
# =========================================================================

def test_docker_executor_command_construction_and_security_flags(monkeypatch):
    """Verify DockerExecutor constructs isolated containers with strict resource limits."""
    executor = DockerExecutor(image_name="test-sandbox:latest")

    # Mock Docker as available
    monkeypatch.setattr(DockerExecutor, "is_docker_available", staticmethod(lambda *args: True))

    captured_cmd = None

    def fake_subprocess_run(cmd, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Rendered 60 frames cleanly."
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

    result = executor.run(
        code="print('hello')",
        smoke_frames=60,
        timeout_seconds=10,
    )

    assert result.status == "PASS"
    assert result.isolation_backend == "docker"
    assert captured_cmd is not None

    cmd_str = " ".join(captured_cmd)
    assert "--network none" in cmd_str, "Must disable network inside the execution container."
    assert "--user 1000:1000" in cmd_str, "Must execute as non-root user."
    assert "--memory 512m" in cmd_str, "Must enforce memory resource limit."
    assert "--cpus 1.0" in cmd_str, "Must enforce CPU resource limit."
    assert "SDL_VIDEODRIVER=dummy" in cmd_str, "Must pass dummy SDL video driver."
    assert ":ro" in cmd_str, "Must mount source code as read-only volume."


def test_docker_executor_handles_container_failure(monkeypatch):
    """Verify DockerExecutor properly captures non-zero exit codes from container."""
    executor = DockerExecutor()
    monkeypatch.setattr(DockerExecutor, "is_docker_available", staticmethod(lambda *args: True))

    def fake_fail_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "Traceback (most recent call last):\nNameError: name 'bad' is not defined"
        return mock_proc

    monkeypatch.setattr(subprocess, "run", fake_fail_run)

    result = executor.run("bad", smoke_frames=60, timeout_seconds=10)

    assert result.status == "FAIL"
    assert result.returncode == 1
    assert "NameError" in result.stderr


def test_docker_executor_handles_container_timeout(monkeypatch):
    """Verify DockerExecutor safely catches timeouts when container hangs."""
    executor = DockerExecutor()
    monkeypatch.setattr(DockerExecutor, "is_docker_available", staticmethod(lambda *args: True))

    def fake_timeout_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10, output="", stderr="timed out")

    monkeypatch.setattr(subprocess, "run", fake_timeout_run)

    result = executor.run("while True: pass", smoke_frames=60, timeout_seconds=10)

    assert result.status == "TIMEOUT"
    assert result.returncode == -1
    assert "timed out after 10 seconds" in result.notes


# =========================================================================
# 3. Delivery Module Tests (Pygbag Web Builds)
# =========================================================================

def test_build_web_package_missing_game_file(tmp_path):
    """Verify build_web_package fails cleanly when source file does not exist."""
    res = build_web_package(tmp_path)
    assert res.success is False
    assert res.status == "BUILD_FAILED"
    assert "not found" in res.notes


def test_build_web_package_when_pygbag_not_installed(tmp_path, monkeypatch):
    """Verify build_web_package reports NOT_INSTALLED when pygbag binary is absent."""
    game_file = tmp_path / "game.py"
    game_file.write_text("import pygame", encoding="utf-8")

    monkeypatch.setattr("shutil.which", lambda prog: None)

    # Force python -m pygbag check to also fail
    def fake_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        return mock_proc

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = build_web_package(tmp_path)
    assert res.success is False
    assert res.status == "NOT_INSTALLED"
    assert "pip install pygbag" in res.notes


def test_build_web_package_successful_simulation(tmp_path, monkeypatch):
    """Verify build_web_package reports SUCCESS when pygbag build passes."""
    game_file = tmp_path / "game.py"
    game_file.write_text("import pygame", encoding="utf-8")

    monkeypatch.setattr("shutil.which", lambda prog: "/usr/bin/pygbag" if prog == "pygbag" else None)

    def fake_success_run(cmd, **kwargs):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Build complete."
        mock_proc.stderr = ""
        return mock_proc

    monkeypatch.setattr(subprocess, "run", fake_success_run)

    res = build_web_package(tmp_path)
    assert res.success is True
    assert res.status == "SUCCESS"
    assert (tmp_path / "web").exists()


# =========================================================================
# 4. Delivery Module Tests (Ngrok Public Sharing)
# =========================================================================

def test_start_ngrok_tunnel_missing_token():
    """Verify start_ngrok_tunnel safely aborts when NGROK_AUTHTOKEN is missing."""
    res = start_ngrok_tunnel(authtoken=None)
    assert res.success is False
    assert res.status == "MISSING_TOKEN"
    assert "NGROK_AUTHTOKEN is not configured" in res.notes


def test_start_ngrok_tunnel_empty_token():
    """Verify start_ngrok_tunnel safely aborts when NGROK_AUTHTOKEN is whitespace."""
    res = start_ngrok_tunnel(authtoken="   ")
    assert res.success is False
    assert res.status == "MISSING_TOKEN"


def test_start_ngrok_tunnel_not_installed(monkeypatch):
    """Verify start_ngrok_tunnel reports NOT_INSTALLED when CLI is missing."""
    monkeypatch.setattr("shutil.which", lambda prog: None)
    with patch.dict("sys.modules", {"pyngrok": None}):
        res = start_ngrok_tunnel(authtoken="dummy_test_token_12345")
    assert res.success is False
    assert res.status == "NOT_INSTALLED"
    # Verify token is NEVER logged in notes
    assert "dummy_test_token_12345" not in res.notes


# =========================================================================
# 5. CLI Delivery Flags Integration Tests
# =========================================================================

def test_cli_handles_web_and_share_flags(tmp_path, capsys, monkeypatch, dummy_success_result):
    """Verify CLI accepts --web and --share flags and dispatches without crashing."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    monkeypatch.setenv("NGROK_AUTHTOKEN", "")

    mock_res = dummy_success_result

    with patch("main.StudioOrchestrator.run", return_value=mock_res):
        exit_code = run_cli([
            "Galactic Defense",
            "--artifacts-dir",
            str(tmp_path / "artifacts"),
            "--web",
            "--share",
        ])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "--web flag requested" in captured.out
    assert "--share flag requested" in captured.out
    assert "MISSING_TOKEN" in captured.out
