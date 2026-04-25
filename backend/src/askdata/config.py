from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    target_db_url: str = "postgresql+asyncpg://askdata_reader:password@localhost:5432/drivee"
    meta_db_url: str = "sqlite+aiosqlite:///./meta.db"

    # Auth
    secret_key: str = "dev-secret-key-change-in-prod"
    access_token_expire_minutes: int = 480
    algorithm: str = "HS256"

    # LLM
    llm_provider: str = "gigachat"
    gigachat_credentials: str = ""
    gigachat_model: str = "GigaChat-Pro"
    local_llm_url: str = ""
    local_llm_model: str = "qwen-coder-7b"
    local_llm_api_key: str = ""
    claude_api_key: str = ""
    claude_model: str = "claude-sonnet-4-6"

    # Demo
    demo_mode: bool = False

    # Telegram
    telegram_bot_token: str = ""

    # Email
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    frontend_url: str = "http://localhost:5173"

    # Pipeline
    template_match_threshold: float = 0.92  # cosine similarity threshold for embedding-based routing
    self_consistency_runs: int = 2  # 2 runs: if agree → SC=1.0; disagree → LLM judge

    sql_timeout_seconds: float = 30.0
    max_rows: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
