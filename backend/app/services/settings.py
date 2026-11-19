from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    upload_dir: Path = Path("../data/raw")
    processed_dir: Path = Path("../data/processed")

    database_url: str = (
        "postgresql+psycopg://insightforge:insightforge_dev@localhost:5432/insightforge"
    )

    # Google Gemini — Primary AI Provider
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"

    # Groq — First Fallback Provider
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-20b"

    # AI Provider Reliability
    ai_provider_timeout_seconds: int = 45
    ai_fallback_enabled: bool = True

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()