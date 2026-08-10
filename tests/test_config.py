"""Settings / config tests: production gate for placeholder secrets."""

import pytest
from pydantic import ValidationError

from app.config import Settings

# Placeholder defaults from app.config
_PLACEHOLDER_JWT = "change-me-to-a-random-secret-at-least-32-chars"
_PLACEHOLDER_ENCRYPTION = "change-me-encryption-key-at-least-32-chars"
_PLACEHOLDER_TG_SECRET = "change-me"


def _make(**overrides) -> Settings:
    """Construct Settings with explicit kwargs, isolated from .env.

    Using `_env_file=None` prevents auto-loading from a real .env on disk.
    """
    kwargs: dict = {
        "_env_file": None,
        "app_env": "development",
        "jwt_secret_key": _PLACEHOLDER_JWT,
        "credentials_encryption_key": _PLACEHOLDER_ENCRYPTION,
        "tg_webhook_secret": _PLACEHOLDER_TG_SECRET,
        "tg_bot_token": None,
    }
    kwargs.update(overrides)
    return Settings(**kwargs)


class TestAppEnv:
    def test_default_is_development(self):
        s = _make()
        assert s.app_env == "development"

    def test_normalises_case(self):
        s = _make(
            app_env="PRODUCTION",
            jwt_secret_key="A" * 40,
            credentials_encryption_key="B" * 40,
        )
        assert s.app_env == "production"

    def test_strips_whitespace(self):
        s = _make(
            app_env="  production  ",
            jwt_secret_key="A" * 40,
            credentials_encryption_key="B" * 40,
        )
        assert s.app_env == "production"


class TestProductionGate:
    def test_development_accepts_placeholders(self):
        """In dev/CI, placeholder secrets remain a convenient default."""
        s = _make()
        assert s.jwt_secret_key == _PLACEHOLDER_JWT
        assert s.credentials_encryption_key == _PLACEHOLDER_ENCRYPTION

    def test_production_rejects_default_jwt_secret(self):
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                credentials_encryption_key="A" * 40,
                tg_webhook_secret="B" * 40,
                tg_bot_token=None,
            )
        assert "JWT_SECRET_KEY" in str(ei.value)

    def test_production_rejects_short_secret(self):
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                jwt_secret_key="tooshort",
                credentials_encryption_key="A" * 40,
                tg_webhook_secret="B" * 40,
                tg_bot_token=None,
            )
        assert "below 32" in str(ei.value)

    def test_production_rejects_default_encryption(self):
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                jwt_secret_key="A" * 40,
                tg_bot_token=None,
            )
        assert "CREDENTIALS_ENCRYPTION_KEY" in str(ei.value)

    def test_production_rejects_default_tg_webhook_secret_when_bot_enabled(self):
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                jwt_secret_key="A" * 40,
                credentials_encryption_key="B" * 40,
                tg_bot_token="real_token",
                tg_webhook_secret="change-me",
            )
        assert "TG_WEBHOOK_SECRET" in str(ei.value)

    def test_production_accepts_strong_secrets_without_bot(self):
        """Strong secrets + no Telegram → production gate passes."""
        s = _make(
            app_env="production",
            jwt_secret_key="A" * 40,
            credentials_encryption_key="B" * 40,
            tg_webhook_secret="change-me",  # ok without tg_bot_token
            tg_bot_token=None,
        )
        assert s.app_env == "production"

    def test_production_accepts_strong_secrets_with_bot(self):
        """Strong secrets + Telegram → production gate passes."""
        s = _make(
            app_env="production",
            jwt_secret_key="A" * 40,
            credentials_encryption_key="B" * 40,
            tg_bot_token="real_token",
            tg_webhook_secret="C" * 40,
        )
        assert s.app_env == "production"
        assert s.tg_bot_token == "real_token"

    def test_error_message_lists_all_offenders(self):
        """All missing/short secrets are reported together."""
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                tg_bot_token="real_token",  # forces TG check
                tg_webhook_secret="change-me",
            )
        msg = str(ei.value)
        assert "JWT_SECRET_KEY" in msg
        assert "CREDENTIALS_ENCRYPTION_KEY" in msg
        assert "TG_WEBHOOK_SECRET" in msg
