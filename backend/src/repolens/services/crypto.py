"""AES-GCM encryption for at-rest secrets (GitHub PAT, Anthropic API key).

Only this module touches the master key. Everywhere else passes opaque
`bytes` blobs. Key is loaded from `REPOLENS_ENCRYPTION_KEY` (32 bytes hex,
64 hex chars). Generate one with:

    python -c "import secrets; print(secrets.token_hex(32))"
"""

from __future__ import annotations

import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..config import get_settings

NONCE_BYTES = 12  # AES-GCM standard


class CryptoError(Exception):
    """Raised when the master key is missing or malformed."""


def _master_key() -> bytes:
    settings = get_settings()
    key_hex = settings.repolens_encryption_key
    if not key_hex:
        raise CryptoError(
            "REPOLENS_ENCRYPTION_KEY not set. Generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    try:
        key = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise CryptoError("REPOLENS_ENCRYPTION_KEY must be hex") from exc
    if len(key) != 32:
        raise CryptoError(
            f"REPOLENS_ENCRYPTION_KEY must be 32 bytes (64 hex chars); got {len(key)}"
        )
    return key


def encrypt(plaintext: str) -> bytes:
    """Encrypt plaintext, return nonce || ciphertext bytes."""
    aesgcm = AESGCM(_master_key())
    nonce = secrets.token_bytes(NONCE_BYTES)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return nonce + ciphertext


def decrypt(blob: bytes) -> str:
    """Decrypt nonce || ciphertext bytes, return plaintext."""
    if len(blob) < NONCE_BYTES + 1:
        raise CryptoError("ciphertext too short")
    aesgcm = AESGCM(_master_key())
    nonce, ciphertext = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


def generate_key() -> str:
    """Convenience for tests / first-run wizard."""
    return secrets.token_hex(32)
