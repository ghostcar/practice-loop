"""Symmetric encryption for LLM API keys using Fernet (cryptography)."""

import base64
import hashlib

from cryptography.fernet import Fernet

from app.config import settings


def _derive_key() -> bytes:
    """Derive a Fernet-compatible 32-byte key from JWT secret."""
    digest = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_fernet = Fernet(_derive_key())


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt an API key. Returns base64-encoded ciphertext."""
    return _fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key. Returns the original plaintext."""
    return _fernet.decrypt(encrypted_key.encode()).decode()


def mask_api_key(encrypted_key: str | None) -> str:
    """Return a masked representation for display. E.g. 'sk-...****'"""
    if not encrypted_key:
        return ""
    try:
        plain = decrypt_api_key(encrypted_key)
        if len(plain) <= 8:
            return "*" * len(plain)
        return plain[:4] + "..." + plain[-4:]
    except Exception:
        return "****"
