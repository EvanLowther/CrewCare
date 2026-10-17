"""Settings read from the repo-root .env file (see .env.example)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_prefix="PLANIT_", extra="ignore")

    database_url: str | None = None
    # Serve sample data from planit/api/mock.py instead of the database.
    mock: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    nws_user_agent: str = "PlanIT Control (hackathon project)"

    # Hazard rules
    lightning_radius_mi: float = 10.0
    lightning_all_clear_min: int = 30


settings = Settings()
