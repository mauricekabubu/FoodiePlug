
"""
apps/ai/services/safety.py

Server-enforced safeguards for FoodiePlug's AI assistant.

Includes message validation, rate limiting, data permissions, bounded
tool-output serialization, prompt-injection flagging, and reply sanitization.
"""

import logging
import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from itertools import islice

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


# =========================================================
# ERRORS
# =========================================================

class SafetyError(Exception):
    """An error that can be safely communicated to the user."""

    def __init__(self, message, code="invalid_request"):
        super().__init__(message)
        self.message = message
        self.code = code


# =========================================================
# SETTINGS
# =========================================================

def _setting(name, default):
    """Read settings at call time so tests and deployments can override them."""
    return getattr(settings, name, default)


def _positive_int_setting(name, default):
    """Read a positive integer setting, falling back on invalid values."""
    try:
        value = int(_setting(name, default))
    except (TypeError, ValueError, OverflowError):
        return default

    return value if value > 0 else default


# =========================================================
# INPUT VALIDATION
# =========================================================

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"ignore (all |any |the )?(previous|prior|above|earlier) "
        r"(instructions|rules|prompts?)",
        r"disregard (all |any |the )?(previous|prior|above|earlier|your) "
        r"(instructions|rules|prompts?)",
        r"(reveal|show|print|repeat|leak) (me )?(your|the) "
        r"(system|hidden|initial|original) (prompt|instructions?)",
        r"you are now (a|an|in)\b",
        r"developer mode",
        r"jailbreak",
        r"bypass (the )?(permissions?|safety|security|rules)",
        r"other users?'? (data|pantry|budget|shopping|meals|conversations?)",
    )
]


def validate_user_message(text):
    """Return a cleaned message or raise SafetyError."""
    if not isinstance(text, str):
        raise SafetyError(
            "Please type a message.",
            code="empty_message",
        )

    # Replace disallowed controls with spaces instead of joining adjacent words.
    cleaned = _CONTROL_CHARS.sub(" ", text).strip()

    if not cleaned:
        raise SafetyError(
            "Please type a message.",
            code="empty_message",
        )

    limit = _positive_int_setting("AI_MAX_MESSAGE_CHARS", 2000)

    if len(cleaned) > limit:
        raise SafetyError(
            f"That message is too long. Please use at most {limit} characters.",
            code="message_too_long",
        )

    return cleaned


def looks_like_prompt_injection(text):
    """
    Flag suspicious wording for additional model context.

    This is a signal, not an authorization check or a reason to bypass
    the backend's normal permission enforcement. The message itself is
    deliberately excluded from logs.
    """
    if not isinstance(text, str) or not text:
        return False

    flagged = any(
        pattern.search(text)
        for pattern in _INJECTION_PATTERNS
    )

    if flagged:
        logger.warning(
            "Potential prompt-injection wording detected in an AI request."
        )

    return flagged


# =========================================================
# RATE LIMITING
# =========================================================

def _hit(key, limit, window_seconds):
    """
    Count one request in a fixed time window.

    Uses the configured Django cache. A shared production cache is required
    for consistent limits across multiple application workers.
    """
    timeout = max(1, int(window_seconds) + 5)

    cache.add(key, 0, timeout=timeout)

    try:
        count = cache.incr(key)
    except ValueError:
        # The key may have expired between add() and incr().
        cache.set(key, 1, timeout=timeout)
        count = 1

    return count <= limit


def check_rate_limit(user_id):
    """Enforce per-minute and per-day request limits for an authenticated user."""
    if user_id is None or not str(user_id).strip():
        raise SafetyError(
            "Please sign in to use the AI assistant.",
            code="authentication_required",
        )

    per_minute = _positive_int_setting("AI_RATE_LIMIT_PER_MINUTE", 10)
    per_day = _positive_int_setting("AI_RATE_LIMIT_PER_DAY", 200)

    now = int(time.time())
    user_key = str(user_id)

    try:
        if not _hit(
            f"ai:rate:min:{user_key}:{now // 60}",
            per_minute,
            60,
        ):
            raise SafetyError(
                "You're sending messages quickly. Please wait a moment "
                "and try again.",
                code="rate_limited",
            )

        if not _hit(
            f"ai:rate:day:{user_key}:{now // 86400}",
            per_day,
            86400,
        ):
            raise SafetyError(
                "You've reached today's limit for AI messages. "
                "Please try again tomorrow.",
                code="daily_limit",
            )

    except SafetyError:
        raise
    except Exception as exc:
        # Fail closed: do not silently disable the rate limit when the
        # cache is unavailable. Log no user message or credentials.
        logger.exception(
            "AI rate-limit cache failed; refusing the request."
        )
        raise SafetyError(
            "The AI assistant is temporarily unavailable. "
            "Please try again shortly.",
            code="rate_limit_unavailable",
        ) from exc


# =========================================================
# DATA PERMISSIONS
# =========================================================

PERMISSION_FIELDS = {
    "pantry": "ai_use_pantry",
    "meals": "ai_use_meals",
    "shopping": "ai_use_shopping",
    "budget": "ai_use_budget",
    "preferences": "ai_use_preferences",
}

# The food catalogue contains shared catalogue data rather than personal
# account records. Keep it available independently of personal-data toggles.
ALWAYS_ALLOWED = {"foods"}

CATEGORY_LABELS = {
    "foods": "the food library",
    "pantry": "pantry",
    "meals": "meals and meal plans",
    "shopping": "shopping lists",
    "budget": "budget and spending",
    "preferences": "food preferences",
}


@dataclass(frozen=True)
class AIPermissions:
    """Which categories of a user's data the AI may read or act on."""

    pantry: bool = True
    meals: bool = True
    shopping: bool = True
    budget: bool = True
    preferences: bool = True

    def allows(self, category):
        if category in ALWAYS_ALLOWED:
            return True

        # Unknown categories and non-boolean truthy values are denied.
        return getattr(self, category, False) is True

    def allows_all(self, categories):
        return all(self.allows(category) for category in categories)

    def disabled(self):
        return [
            category
            for category in PERMISSION_FIELDS
            if not self.allows(category)
        ]


NO_ACCESS = AIPermissions(
    pantry=False,
    meals=False,
    shopping=False,
    budget=False,
    preferences=False,
)


def _coerce_permission(value, default):
    """Normalize stored permission values without treating 'False' as True."""
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    if isinstance(value, int) and value in (0, 1):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "on"}:
            return True

        if normalized in {"false", "0", "no", "off"}:
            return False

    # Malformed permission values should never grant access.
    return False


def get_permissions(user):
    """
    Return the user's effective AI data permissions.

    Compatibility behavior: missing profile fields default to True unless
    AI_DEFAULT_PERMISSION_ALLOWED=False is configured. Once the settings
    toggles are implemented, production deployments should explicitly
    choose their desired default.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return NO_ACCESS

    profile = getattr(user, "profile", None)
    default_allowed = _coerce_permission(
        _setting("AI_DEFAULT_PERMISSION_ALLOWED", True),
        True,
    )

    values = {}

    for category, field in PERMISSION_FIELDS.items():
        raw_value = (
            getattr(profile, field, None)
            if profile is not None
            else None
        )

        values[category] = _coerce_permission(
            raw_value,
            default_allowed,
        )

    return AIPermissions(**values)


# =========================================================
# TOOL OUTPUT CLEANING
# =========================================================

MAX_STRING_CHARS = 300
MAX_COLLECTION_ITEMS = 100
MAX_NESTING_DEPTH = 6
TRUNCATION_MARKER = {"_tool_output_truncated": True}


def to_model_safe(value, max_string=MAX_STRING_CHARS, _depth=0):
    """
    Convert tool output to bounded, plain JSON-compatible data.

    Limits string lengths, collection sizes, dictionary key lengths, and
    nesting depth. Non-finite numbers become None.
    """
    if _depth > MAX_NESTING_DEPTH:
        return None

    try:
        max_string = max(1, int(max_string))
    except (TypeError, ValueError, OverflowError):
        max_string = MAX_STRING_CHARS

    if value is None or isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value

    if isinstance(value, (float, Decimal)):
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return None

        if not math.isfinite(number):
            return None

        return int(number) if number.is_integer() else round(number, 3)

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, str):
        cleaned = _CONTROL_CHARS.sub("", value)

        if len(cleaned) <= max_string:
            return cleaned

        return cleaned[: max_string - 1] + "…"

    if isinstance(value, dict):
        # Consume no more than one extra item to detect truncation.
        items = list(islice(value.items(), MAX_COLLECTION_ITEMS + 1))
        truncated = len(items) > MAX_COLLECTION_ITEMS
        result = {}

        for key, item_value in items[:MAX_COLLECTION_ITEMS]:
            safe_key = _CONTROL_CHARS.sub("", str(key))[:100] or "field"

            # Reserve our metadata key for the truncation indicator.
            if safe_key == "_tool_output_truncated":
                safe_key = "_source_tool_output_truncated"

            result[safe_key] = to_model_safe(
                item_value,
                max_string=max_string,
                _depth=_depth + 1,
            )

        if truncated:
            result["_tool_output_truncated"] = True

        return result

    if isinstance(value, (list, tuple, set)):
        items = list(islice(iter(value), MAX_COLLECTION_ITEMS + 1))
        truncated = len(items) > MAX_COLLECTION_ITEMS

        result = [
            to_model_safe(
                item,
                max_string=max_string,
                _depth=_depth + 1,
            )
            for item in items[:MAX_COLLECTION_ITEMS]
        ]

        if truncated:
            result.append(dict(TRUNCATION_MARKER))

        return result

    # Avoid exposing arbitrary object representations without bounds.
    return to_model_safe(
        str(value),
        max_string=max_string,
        _depth=_depth + 1,
    )


# =========================================================
# REPLY CLEAN-UP AND SECRET REDACTION
# =========================================================

_KEY_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
]

FALLBACK_REPLY = (
    "I couldn't put an answer together just now. Please try asking again."
)
MAX_REPLY_CHARS = 8000


def redact_secrets(text):
    """Remove configured Gemini keys and strings matching Google API-key syntax."""
    if not isinstance(text, str):
        return ""

    configured = _setting("GEMINI_API_KEY", "")

    if isinstance(configured, str) and len(configured) > 8:
        text = text.replace(configured, "[redacted]")

    for pattern in _KEY_PATTERNS:
        text = pattern.sub("[redacted]", text)

    return text


def finalize_reply(text):
    """Sanitize a generated reply before displaying it to the user."""
    if not isinstance(text, str):
        text = ""

    text = _CONTROL_CHARS.sub("", text).strip()
    text = redact_secrets(text)

    if not text:
        return FALLBACK_REPLY

    if len(text) > MAX_REPLY_CHARS:
        text = text[: MAX_REPLY_CHARS - 1].rstrip() + "…"

    return text
