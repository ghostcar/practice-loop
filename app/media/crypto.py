"""AES-256-GCM Encrypted Media Vault Storage at Rest (Step 1)."""

from __future__ import annotations

import logging
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)


def generate_vault_encryption_key() -> bytes:
    """Generates 256-bit AES-GCM secret key."""
    return AESGCM.generate_key(bit_length=256)


def encrypt_media_bytes(data: bytes, key: bytes) -> bytes:
    """Encrypts raw media bytes using AES-256-GCM and prepends 12-byte nonce."""
    if len(key) != 32:
        raise ValueError("Key must be exactly 32 bytes (256 bits).")

    aesgcm = AESGCM(key)
    nonce = secrets.token_bytes(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext


def decrypt_media_bytes(encrypted_data: bytes, key: bytes) -> bytes:
    """Decrypts AES-256-GCM encrypted media bytes."""
    if len(key) != 32:
        raise ValueError("Key must be exactly 32 bytes (256 bits).")

    if len(encrypted_data) < 28:  # 12 nonce + 16 tag minimum
        raise ValueError("Encrypted data is too short.")

    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)
