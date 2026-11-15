from app.config import Settings


def test_settings_defaults():
    settings = Settings()
    assert settings.app_name == "Talox Tech Stream"
    assert settings.app_env in ["development", "staging", "production"]
    assert settings.rate_limit_agent_rpm == 20
    assert settings.circuit_breaker_max_failures == 3
    assert settings.ai_default_fast_model == "deepseek-chat"
    assert settings.ai_default_reasoning_model == "deepseek-reasoner"
