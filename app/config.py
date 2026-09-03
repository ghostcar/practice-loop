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
_PLACEHOLDER_CHALLENGE = "change-me-challenge-hmac-key-at-least-32-chars"
_PLACEHOLDER_TG_SECRET = "change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment toggle: production | development (default). Read from APP_ENV env var.
    app_env: str = "development"

    # Product variant: tracker | timer | combined (ADR-043).
    # Defaults to "combined" for existing upgrades; fresh deploys should set explicitly.
    app_product_variant: str = "combined"

    # Feature flags — all default OFF for safe rollout (03A_PRODUCT_VARIANTS.md §7).
    locktimer_core_enabled: bool = False
    locktimer_verification_enabled: bool = False
    social_enabled: bool = True
    social_tracker_adapter_enabled: bool = False
    social_timer_adapter_enabled: bool = False
    social_public_enabled: bool = True
    locktimer_keyholder_enabled: bool = False
    locktimer_cloud_media_enabled: bool = False

    # Dynamic Monetization Feature Flag (default False for open free portal)
    monetization_enabled: bool = False

    # Community creation limit per user (0 = unlimited). Reserved for future monetization.
    community_creation_limit: int = 3

    # Experimental draft models (ADR-R1.2) — behind flags for safe rollout.
    experimental_leagues: bool = False
    experimental_billing: bool = False

    # M3 Personal Suite (Шаг 11b) — Medication Organizer. Health-модуль, relief-only.
    medication_enabled: bool = True

    # M3 Personal Suite (Шаг 13) — Health + Cycle foundation (4D). Health-модуль, relief-only.
    health_enabled: bool = True

    # M3 Personal Suite (Шаг 14) — Sexual Journal (4A). Приватный журнал, relief-only.
    journal_enabled: bool = True

    # M3 Personal Suite (Шаг 15) — Personal Care (4B). Уход/процедуры, relief-only.
    care_enabled: bool = True

    # Сквозной каталог активностей (ADR-091) — единый справочник видов активностей,
    # на который ссылаются журнал/уход/таймер/трекер. Нейтрален (relief-only).
    catalog_enabled: bool = True

    # M3 Personal Suite (Шаг 17) — Personal Insights (4E). Кросс-модульный LLM-
    # анализ личных данных (явно запрошенный), relief-only.
    insights_enabled: bool = True

    # Aftercare (C1) — отдельный модуль заботы после сцены. Relief-only (PD-013).
    aftercare_enabled: bool = True

    # Consent records (C3) — согласия на чувствительную обработку данных.
    consent_enabled: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://tracker:tracker@localhost:5432/tracker"

    # JWT
    jwt_secret_key: str = _PLACEHOLDER_JWT
    jwt_algorithm: str = "HS256"
    # Browser access cookie lifetime. Refresh-token rotation keeps sessions alive
    # across restarts without ever persisting a password in the browser.
    jwt_expire_minutes: int = 60 * 24 * 30  # 30 days

    # Mobile Foundation (M4): opaque refresh tokens (sliding window).
    refresh_token_expire_days: int = 90

    # Push notifications (M4). none = disabled; logging = log-only (dev).
    # fcm/apns become real senders once provider credentials exist.
    push_provider: str = "none"

    # Encryption (separate from JWT)
    credentials_encryption_key: str = _PLACEHOLDER_ENCRYPTION

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Uploads (user media: inventory photos, photo reports).
    # Relative to the app working dir; mounted as a named volume in docker-compose.
    upload_dir: str = "uploads"
    max_upload_bytes: int = 8 * 1024 * 1024  # 8 MB

    # Universal media (media_assets table — platform-level, not Timer-specific).
    media_max_upload_bytes: int = 15 * 1024 * 1024  # 15 MB per media asset
    challenge_hmac_key: str = _PLACEHOLDER_CHALLENGE  # separate key for verification challenge HMAC

    # Owner allowlist for staged rollout (14_ROLLOUT_OPERATIONS.md §1).
    # Comma-separated email list; empty = no restriction.
    locktimer_owner_allowlist: str = ""

    # Omniroute — local LLM proxy (BYOK default provider, ADR-002/ADR-070).
    # Same vars are used by the memory vector pilot (tools/memoryctl, ADR-069).
    omniroute_host: str | None = None
    omniroute_api_key: str | None = None
    omniroute_embedding_model: str = "openrouter/openai/text-embedding-3-small"

    # Portal LLM catalog. Metadata and credentials are supplied from .env;
    # never commit this value. JSON shape: [{"name":"...","base_url":"...",
    # "api_key":"...","models":[{"name":"...","vision":true}]}]
    portal_llm_providers_json: str = "[]"

    # Sections where personal BYOK providers are allowed. Empty means none;
    # JSON array, e.g. ["tasks", "training"]. Portal remains available everywhere.
    personal_llm_sections_json: str = "[]"

    # Telegram
    tg_bot_token: str | None = None
    tg_webhook_secret: str = _PLACEHOLDER_TG_SECRET
    tg_webhook_base_url: str = "https://localhost:8443"
    tg_bot_username: str = "practice_loop_bot"
    tg_polling: bool = False  # True = polling mode (local dev), False = webhook
    tg_auto_analysis_time: str = "23:00"  # HH:MM — when to run end-of-day training analysis
    tg_auto_analysis_tz: str = "UTC"  # IANA timezone for the analysis time + "today" day boundary

    # Reminder engine (ADR-095) — medication/care/timer reminders via
    # Telegram + in-app + push. relief-only (PD-013).
    reminder_enabled: bool = True
    reminder_time: str = "09:00"  # HH:MM — daily reminder cycle
    reminder_tz: str = "UTC"  # IANA timezone for the reminder time
    # Event reminders (ADR-096): "shortly before" notifications fire on a
    # faster cadence than the daily batch. The event loop runs every
    # reminder_event_interval_minutes and notifies reminder_event_lead_minutes
    # ahead of the event (timer window opening, task due, medication dose time).
    reminder_event_interval_minutes: int = 15
    reminder_event_lead_minutes: int = 30

    @field_validator("app_env")
    @classmethod
    def _normalize_env(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("app_product_variant")
    @classmethod
    def _validate_variant(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("tracker", "timer", "combined"):
            raise ValueError(f"APP_PRODUCT_VARIANT must be 'tracker', 'timer', or 'combined', got '{v}'")
        return v

    @model_validator(mode="after")
    def _validate_variant_consistency(self) -> "Settings":
        """Reject timer variant with disabled timer core (03A_PRODUCT_VARIANTS.md §4).

        The only exception is APP_MAINTENANCE_MODE=true (explicit deploy operation).
        """
        maintenance = getattr(self, "app_maintenance_mode", False)
        if self.app_product_variant == "timer" and not self.locktimer_core_enabled and not maintenance:
            raise ValueError(
                "APP_PRODUCT_VARIANT=timer requires LOCKTIMER_CORE_ENABLED=true or APP_MAINTENANCE_MODE=true"
            )
        return self

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
        if self.challenge_hmac_key == _PLACEHOLDER_CHALLENGE:
            offenders.append("CHALLENGE_HMAC_KEY")
        # TG_WEBHOOK_SECRET only required when TG bot is configured.
        if self.tg_bot_token and self.tg_webhook_secret == _PLACEHOLDER_TG_SECRET:
            offenders.append("TG_WEBHOOK_SECRET")

        # Length sanity (SPEC requirement: secrets ≥32 chars).
        # An empty CHALLENGE_HMAC_KEY is also rejected here (len < 32) so the
        # old "default-challenge-key" fallback can never activate in production.
        for name, val in (
            ("JWT_SECRET_KEY", self.jwt_secret_key),
            ("CREDENTIALS_ENCRYPTION_KEY", self.credentials_encryption_key),
            ("CHALLENGE_HMAC_KEY", self.challenge_hmac_key),
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
