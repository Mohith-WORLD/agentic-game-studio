"""
Unit tests for configuration and settings.
"""

from config.settings import Settings, load_settings


def test_default_settings():
    s = Settings()
    assert s.max_repair_attempts == 2
    assert s.smoke_test_frames == 60
    assert s.execution_timeout_seconds == 10
    assert s.model_name == "gemini-2.5-flash"
    assert not s.has_gemini_key
    assert "GEMINI_API_KEY" in s.missing_required_keys()
    assert not s.is_configured_for_generation()


def test_masking_secrets():
    s = Settings(
        gemini_api_key="mock_artificial_test_gemini_key_12345",
        ngrok_authtoken="mock_artificial_test_ngrok_token_67890",
    )
    report = s.get_status_report()
    assert "mock_artificial_test_gemini_key_12345" not in report["GEMINI_API_KEY"]
    assert "..." in report["GEMINI_API_KEY"]
    assert "mock_artificial_test_ngrok_token_67890" not in report["NGROK_AUTHTOKEN"]
    assert "..." in report["NGROK_AUTHTOKEN"]
    assert report["is_ready_for_llm"] is True


def test_load_settings_env_override(monkeypatch):
    monkeypatch.setenv("MAX_REPAIR_ATTEMPTS", "2")
    monkeypatch.setenv("SMOKE_TEST_FRAMES", "120")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    
    s = load_settings()
    assert s.max_repair_attempts == 2
    assert s.smoke_test_frames == 120
    assert s.model_name == "gemini-2.5-flash"
