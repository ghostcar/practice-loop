from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql+asyncpg://tracker:tracker@localhost:5432/tracker"

    # JWT
    jwt_secret_key: str = "change-me-to-a-random-secret-at-least-32-chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24 hours

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Telegram
    tg_bot_token: str | None = None
    tg_webhook_secret: str = "change-me"
    tg_webhook_base_url: str = "https://localhost:8443"
    tg_bot_username: str = "practice_loop_bot"
    tg_polling: bool = False  # True = polling mode (local dev), False = webhook
    tg_auto_analysis_time: str = "23:00"  # HH:MM UTC — when to run end-of-day training analysis


settings = Settings()
