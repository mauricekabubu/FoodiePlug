
"""Helpers for a user's Gemini configuration."""

import logging

from django.utils import timezone

from apps.ai.models import UserAIConfig
from .credentials import encrypt_api_key, decrypt_api_key

logger = logging.getLogger(__name__)

# Keep this list explicit; only offer models you've chosen to support.
GEMINI_MODELS = {
    "gemini-3.8-flash": "Gemini 3.8 Flash",
    "gemini-3.6-flash": "Gemini 3.6 Flash",
    "gemini-2.5-flash": "Gemini 2.5 Flash (legacy)",
}


def get_user_ai_config(user):
    config, _ = UserAIConfig.objects.get_or_create(user=user)
    return config


def save_user_api_key(config, api_key):
    config.encrypted_api_key = encrypt_api_key(api_key)
    config.connection_status = "untested"
    config.connection_test_succeeded = False
    config.connection_tested_at = None
    config.save(update_fields=[
        "encrypted_api_key",
        "connection_status",
        "connection_test_succeeded",
        "connection_tested_at",
        "updated_at",
    ])


def remove_user_api_key(config):
    config.encrypted_api_key = ""
    config.connection_status = "untested"
    config.connection_test_succeeded = False
    config.connection_tested_at = None
    config.save(update_fields=[
        "encrypted_api_key",
        "connection_status",
        "connection_test_succeeded",
        "connection_tested_at",
        "updated_at",
    ])


def test_user_api_key(config):
    """Make a small provider request without exposing the key to the browser."""
    if not config.encrypted_api_key:
        return False, "Save a Gemini API key before testing the connection."

    try:
        api_key = decrypt_api_key(config.encrypted_api_key)

        from google import genai  # type: ignore[import-not-found]
        from google.genai import types  # type: ignore[import-not-found]

        client = genai.Client(api_key=api_key)
        client.models.generate_content(
            model=config.model_name,
            contents="Reply with OK.",
            config=types.GenerateContentConfig(max_output_tokens=8),
        )

    except Exception as exc:
        # Do not log exception text; it may contain sensitive provider details.
        logger.warning(
            "Gemini connection test failed for user %s (%s).",
            config.user_id,
            type(exc).__name__,
        )
        config.connection_status = "failed"
        config.connection_test_succeeded = False
        config.connection_tested_at = timezone.now()
        config.save(update_fields=[
            "connection_status",
            "connection_test_succeeded",
            "connection_tested_at",
            "updated_at",
        ])
        return False, (
            "Connection test failed. Check your API key, selected model, "
            "Google AI API access, and available quota."
        )

    config.connection_status = "success"
    config.connection_test_succeeded = True
    config.connection_tested_at = timezone.now()
    config.save(update_fields=[
        "connection_status",
        "connection_test_succeeded",
        "connection_tested_at",
        "updated_at",
    ])
    return True, "Gemini connection successful."
