"""本机 Agent 配置。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_base_url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    # 兼容旧字段；优先 api_key
    api_token: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    machine_id: str = "local-pc"
    browser_user_data_dir: str = "./data/browser-profile"
    browser_channel: str = ""
    screenshot_dir: str = "./data/screenshots"
    download_dir: str = "./data/downloads"
    selectors_path: str = ""
    open_detail_for_segments: bool = True
    wait_attachment_after_greet: bool = True
