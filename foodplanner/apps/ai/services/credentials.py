
"""Secure storage helpers for users' third-party API credentials."""

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class CredentialEncryptionError(Exception):
    """Raised when credentials cannot be safely encrypted or decrypted."""


def _fernet():
    key = getattr(
        settings,
        "FOODIEPLUG_CREDENTIALS_ENCRYPTION_KEY",
        "",
    )

    if not key:
        raise CredentialEncryptionError(
            "Credential encryption is not configured."
        )

    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (TypeError, ValueError) as exc:
        raise CredentialEncryptionError(
            "The credential encryption key is invalid."
        ) from exc


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key before storing it in the database."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("An API key is required.")

    try:
        return _fernet().encrypt(api_key.strip().encode()).decode()
    except CredentialEncryptionError:
        raise
    except Exception as exc:
        raise CredentialEncryptionError(
            "The API key could not be encrypted."
        ) from exc


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt a stored API key for server-side provider requests."""
    if not encrypted_key:
        return ""

    try:
        return _fernet().decrypt(encrypted_key.encode()).decode()
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise CredentialEncryptionError(
            "The stored API key could not be decrypted."
        ) from exc
