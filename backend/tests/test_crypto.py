"""AES-GCM crypto round-trip tests.

Sets the master key in env before importing the module so get_settings()
picks it up. We clear the lru_cache between tests to keep cases isolated.
"""

from __future__ import annotations

import secrets

import pytest

from repolens.config import Settings, get_settings
from repolens.services import crypto
from repolens.services.crypto import CryptoError, decrypt, encrypt, generate_key


def _set_key(monkeypatch, key: str | None) -> None:
    """Override the crypto module's view of Settings.

    Bypasses pydantic-settings' .env loading so tests can simulate "no key"
    even when the dev .env file has one set.
    """

    def fake_get_settings() -> Settings:
        return Settings(_env_file=None, repolens_encryption_key=key)  # type: ignore[call-arg]

    monkeypatch.setattr(crypto, "get_settings", fake_get_settings)


def test_round_trip_recovers_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, generate_key())
    plaintext = "ghp_super_secret_pat_value_42"
    blob = encrypt(plaintext)
    assert blob != plaintext.encode()
    assert decrypt(blob) == plaintext


def test_each_encrypt_uses_a_fresh_nonce(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, generate_key())
    blob_a = encrypt("same plaintext")
    blob_b = encrypt("same plaintext")
    assert blob_a != blob_b  # nonces differ → ciphertexts differ
    assert decrypt(blob_a) == decrypt(blob_b) == "same plaintext"


def test_decrypt_with_wrong_key_raises_cryptoerror(monkeypatch: pytest.MonkeyPatch) -> None:
    """A wrong key must surface as CryptoError, not the underlying InvalidTag.

    Callers (the CLI in particular) catch CryptoError to render a helpful
    message; the wrap means they don't need to know about cryptography internals.
    """
    _set_key(monkeypatch, generate_key())
    blob = encrypt("hello")
    _set_key(monkeypatch, generate_key())
    with pytest.raises(CryptoError, match="decryption failed"):
        decrypt(blob)


def test_missing_key_raises_cryptoerror(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, None)
    with pytest.raises(CryptoError, match="not set"):
        encrypt("anything")


def test_short_key_raises_cryptoerror(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, secrets.token_hex(16))  # 16 bytes, not 32
    with pytest.raises(CryptoError, match="32 bytes"):
        encrypt("anything")


def test_non_hex_key_raises_cryptoerror(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, "not hex at all xyz")
    with pytest.raises(CryptoError, match="hex"):
        encrypt("anything")


def test_truncated_blob_raises_cryptoerror(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_key(monkeypatch, generate_key())
    with pytest.raises(CryptoError, match="too short"):
        decrypt(b"ab")


@pytest.fixture(autouse=True)
def _restore_settings_cache() -> None:
    """Ensure other tests see the .env-loaded settings, not whatever a crypto
    test set last."""
    yield
    get_settings.cache_clear()
