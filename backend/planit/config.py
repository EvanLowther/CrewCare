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
    gemini_model: str = "gemini-3.5-flash"
    # Tried in order when the model above is retired (404) or overloaded (503), comma-separated.
    gemini_fallback_models: str = "gemini-3.5-flash,gemini-3.7-flash,gemini-flash-latest"
    nws_user_agent: str = "Crew Care (hackathon project)"

    # Hazard score: "xgb" uses the trained model in planit/ml/models/ (falls back to rules-v1 without one),
    # "rules" forces rules-v1.
    score_model: str = "xgb"

    # Login (docs/AUTH.md). The API checks Auth0 access tokens issued for this audience.
    auth0_domain: str | None = None  # e.g. planit-control.us.auth0.com
    auth0_audience: str | None = None  # the Auth0 API identifier, e.g. https://api.planit-control
    # Comma-separated emails that are always admin once Auth0 has verified them.
    admin_emails: str = ""
    # Laptops and CI only: accept "Authorization: Dev <admin|manager|crew|...>" from the "Sign in as" menu.
    # Never set on the server.
    auth_dev: bool = False
    # Signs photo URLs so <img> tags (which can't send a token) only load photos the viewer may see.
    photo_signing_key: str = "dev-only-photo-key"

    # Hazard rules
    lightning_radius_mi: float = 10.0
    lightning_all_clear_min: int = 30


settings = Settings()


def admin_email_set() -> set[str]:
    return {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
