"""
Configuration and settings management for Agentic Game Studio.
"""

import os
from dataclasses import dataclass
from typing import List, Optional
from dotenv import load_dotenv


@dataclass
class Settings:
    """Application settings and environment credential management."""
    gemini_api_key: Optional[str] = None
    ngrok_authtoken: Optional[str] = None
    model_name: str = "gemini-2.5-flash"
    max_repair_attempts: int = 2
    smoke_test_frames: int = 60
    execution_timeout_seconds: int = 10
    artifacts_dir: str = "artifacts"

    def __post_init__(self):
        if self.max_repair_attempts > 2:
            self.max_repair_attempts = 2
        elif self.max_repair_attempts < 0:
            self.max_repair_attempts = 0

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    @property
    def has_ngrok_token(self) -> bool:
        return bool(self.ngrok_authtoken and self.ngrok_authtoken.strip())

    def missing_required_keys(self) -> List[str]:
        missing = []
        if not self.has_gemini_key:
            missing.append("GEMINI_API_KEY")
        return missing

    def is_configured_for_generation(self) -> bool:
        return len(self.missing_required_keys()) == 0

    @staticmethod
    def _mask(val: Optional[str]) -> str:
        if not val:
            return "Not Configured"
        v = val.strip()
        if len(v) <= 8:
            return "***"
        return f"{v[:4]}...{v[-4:]}"

    def get_status_report(self) -> dict:
        return {
            "GEMINI_API_KEY": self._mask(self.gemini_api_key),
            "NGROK_AUTHTOKEN": self._mask(self.ngrok_authtoken),
            "GEMINI_MODEL": self.model_name,
            "MAX_REPAIR_ATTEMPTS": self.max_repair_attempts,
            "SMOKE_TEST_FRAMES": self.smoke_test_frames,
            "EXECUTION_TIMEOUT_SECONDS": self.execution_timeout_seconds,
            "is_ready_for_llm": self.is_configured_for_generation(),
        }


def load_settings(env_path: Optional[str] = None) -> Settings:
    """Load settings from environment variables and optional .env file."""
    if env_path and os.path.exists(env_path):
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    ngrok_token = os.getenv("NGROK_AUTHTOKEN")
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    try:
        max_repairs = int(os.getenv("MAX_REPAIR_ATTEMPTS", "2"))
    except ValueError:
        max_repairs = 2

    try:
        smoke_frames = int(os.getenv("SMOKE_TEST_FRAMES", "60"))
    except ValueError:
        smoke_frames = 60

    try:
        timeout = int(os.getenv("EXECUTION_TIMEOUT_SECONDS", "10"))
    except ValueError:
        timeout = 10

    artifacts_dir = os.getenv("ARTIFACTS_DIR", "artifacts")

    return Settings(
        gemini_api_key=gemini_key,
        ngrok_authtoken=ngrok_token,
        model_name=model_name,
        max_repair_attempts=max_repairs,
        smoke_test_frames=smoke_frames,
        execution_timeout_seconds=timeout,
        artifacts_dir=artifacts_dir,
    )
