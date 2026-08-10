"""Application config.

Production gate: when APP_ENV=production, placeholder secrets (`change-me-...`)
are rejected at startup. Set APP_ENV=development (default) for dev/CI to keep
these defaults useful.

Reference: REMEDIATION_SPEC.md §9.1 «production завершается с понятной ошибкой при placeholder».
"""

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder strings that must NEVER appear in a production deployment.
_PLACEHOLDER_JWT = "change-me-to-a-random-secret-at-least-32-chars"
_PLACEHOLDER_ENCRYPTION = "change-me-encryption-key-at-least-32-chars"
_PLACEHOLDER_TG_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment toggle: production | development (default). Read from APP_ENV env var.
    app_env: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://tracker:tracker@localhost:5432/tracker"

    # JWT
    jwt_secret_key: str = _PLACEHOLDER_JWT
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # Encryption (separate from JWT)
    credentials_encryption_key: str = _PLACEHOLDER_ENCRYPTION

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Uploads (user media: inventory photos, photo reports).
    # Relative to the app working dir; mounted as a named volume in docker-compose.
    upload_dir: str = "uploads"
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 MB

    # Telegram
    tg_bot_token: str | None = None
    tg_webhook_secret: str = _PLACEHOLDER_TG_SECRET
    tg_webhook_base_url: str = "https://localhost:8443"
    tg_bot_username: str = "practice_loop_bot"
    tg_polling: bool = False  # True = polling mode (local dev), False = webhook
    tg_auto_analysis_time: str = "23:00"  # HH:MM UTC — when to run end-of-day training analysis

    @field_validator("app_env")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.strip().lower()

    @model_validator(mode="after")
    def _reject_placeholders_in_production(self) -> "Settings":
        """In production, refuse to start with default placeholder secrets.

        In development/CI the defaults are convenient; only production is hardened.
        """
        if self.app_env != "production":
            return self

        offenders: list[str] = []
        if self.jwt_secret_key == _PLACEHOLDER_JWT:
            offenders.append("JWT_SECRET_KEY")
        if self.credentials_encryption_key == _PLACEHOLDER_ENCRYPTION:
            offenders.append("CREDENTIALS_ENCRYPTION_KEY")
        # TG_WEBHOOK_SECRET only required when TG bot is configured.
        if self.tg_bot_token and self.tg_webhook_secret == _PLACEHOLDER_TG_SECRET:
            offenders.append("TG_WEBHOOK_SECRET")

        # Length sanity (SPEC requirement: secrets ≥32 chars).
        for name, val in (
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("CREDENTIALS_ENCRYPTION_KEY", self.credentials_encryption_key),
        ):
            if name not in offenders and len(val) < 32:
                offenders.append(f"{name} (below 32 chars)")

        if offenders:
            raise ValueError(
                "APP_ENV=production refuses placeholder/short secrets. "
                "Set the following env vars to strong random values (≥32 chars): " + ", ".join(offenders)
            )
        return self


settings = Settings()
