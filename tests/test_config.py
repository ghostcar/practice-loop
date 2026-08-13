"""Settings / config tests: production gate for placeholder secrets."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings

# Placeholder defaults from app.config
_PLACEHOLDER_JWT = "change-me-to-a-random-secret-at-least-32-chars"
_PLACEHOLDER_ENCRYPTION = "change-me-encryption-key-at-least-32-chars"
_PLACEHOLDER_CHALLENGE = "change-me-challenge-hmac-key-at-least-32-chars"
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
        "challenge_hmac_key": _PLACEHOLDER_CHALLENGE,
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
            challenge_hmac_key="C" * 40,
        )
        assert s.app_env == "production"

    def test_strips_whitespace(self):
        s = _make(
            app_env="  production  ",
            jwt_secret_key="A" * 40,
            credentials_encryption_key="B" * 40,
            challenge_hmac_key="C" * 40,
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
            challenge_hmac_key="C" * 40,
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
            challenge_hmac_key="C" * 40,
            tg_bot_token="real_token",
            tg_webhook_secret="D" * 40,
        )
        assert s.app_env == "production"
        assert s.tg_bot_token == "real_token"

    def test_production_rejects_default_challenge_key(self):
        """Audit P0-2: the placeholder challenge HMAC key must be rejected in prod."""
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                jwt_secret_key="A" * 40,
                credentials_encryption_key="B" * 40,
                tg_bot_token=None,
            )
        assert "CHALLENGE_HMAC_KEY" in str(ei.value)

    def test_production_rejects_empty_challenge_key(self):
        """An empty CHALLENGE_HMAC_KEY (old fallback trigger) must be rejected in prod."""
        with pytest.raises(ValidationError) as ei:
            _make(
                app_env="production",
                jwt_secret_key="A" * 40,
                credentials_encryption_key="B" * 40,
                challenge_hmac_key="",
                tg_bot_token=None,
            )
        assert "CHALLENGE_HMAC_KEY" in str(ei.value)

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


class TestSeedScriptsNoHardcodedCredentials:
    """Regression: seed scripts must not embed real DB credentials (audit S51).

    A hardcoded `tracker_dev_2024` password was found in seed_prod.py and
    seed_training.py and later purged from git history. These tests make sure
    it never comes back.
    """

    SEED_FILES = [
        Path(__file__).resolve().parent.parent / "seed_prod.py",
        Path(__file__).resolve().parent.parent / "seed_training.py",
    ]

    def test_no_real_password_in_seed_files(self):
        for path in self.SEED_FILES:
            content = path.read_text(encoding="utf-8")
            assert "tracker_dev_2024" not in content, f"leaked password in {path}"

    def test_no_database_url_with_embedded_credentials(self):
        """Seeds must not hardcode any user:password@ in a connection string."""
        import re

        cred_re = re.compile(r"postgres(?:ql|\+asyncpg)?://[^@\s:]+:[^@\s]+@")
        for path in self.SEED_FILES:
            content = path.read_text(encoding="utf-8")
            assert not cred_re.search(content), f"credentials embedded in {path}"

    def test_seed_scripts_refuse_without_database_url(self):
        """Both seeds must fail fast when DATABASE_URL is missing."""
        for path in self.SEED_FILES:
            content = path.read_text(encoding="utf-8")
            assert "DATABASE_URL" in content
            assert "sys.exit(1)" in content

    def _run_without_env(self, script: str, *args: str) -> subprocess.CompletedProcess:
        """Run a seed script with DATABASE_URL removed from the environment."""
        env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
        return subprocess.run(
            [sys.executable, script, *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parent.parent,
            timeout=30,
        )

    def test_seed_training_fails_fast_without_database_url(self):
        """seed_training.py exits 1 before any DB work when DATABASE_URL is unset."""
        proc = self._run_without_env(str(self.SEED_FILES[1]))
        assert proc.returncode == 1
        assert "DATABASE_URL" in proc.stderr

    def test_seed_prod_accepts_explicit_database_url_flag(self):
        """Regression (reviewer): --database-url must work even without DATABASE_URL env.

        The script should get past the credential check and fail on connection
        (fast-refused localhost port), proving the flag is not dead code.
        """
        proc = self._run_without_env(
            str(self.SEED_FILES[0]),
            "--database-url",
            "postgresql+asyncpg://user:pass@127.0.0.1:1/db",
        )
        assert proc.returncode != 0
        assert "DATABASE_URL is not set" not in proc.stderr
