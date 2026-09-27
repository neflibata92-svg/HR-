from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_production_compose_requires_secrets_and_keeps_api_internal() -> None:
    compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?" in compose
    assert "JWT_SECRET: ${JWT_SECRET:?" in compose
    assert "CORS_ORIGINS: ${CORS_ORIGINS:?" in compose
    assert "ALLOW_REGISTER: ${ALLOW_REGISTER:-false}" in compose
    assert "LLM_API_KEY: ${LLM_API_KEY:-}" in compose
    assert "\n      API_KEY:" not in compose
    assert '"8000:8000"' not in compose


def test_env_example_separates_server_and_agent_secrets() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "# API 服务器专用" in env_example
    assert "# 本机 Agent 专用" in env_example
    assert "LLM_API_KEY=" in env_example
    assert "API_KEY=" in env_example
    assert "BROWSER_USER_DATA_DIR=" in env_example
    assert "SCREENSHOT_DIR=" in env_example
    assert "DOWNLOAD_DIR=" in env_example
