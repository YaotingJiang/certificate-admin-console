from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    app_name: str = "Certificate Admin Console"
    db_path: str = str(BACKEND_DIR / "data" / "app.db")
    cors_origins: list[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_")


settings = Settings()
