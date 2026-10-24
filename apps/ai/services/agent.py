"""
apps/ai/services/agent.py — FoodiePlug AI, powered by Google Gemini.

    reply = get_agent().respond(request.user, "Nipangie meals za wiki", conversation_id=None)
    reply.text, reply.conversation_id, reply.pending_actions

One call to respond() does this, in order:
  1. validate the message and apply per-user rate limits           (safety.py)
  2. work out which data the user allows the AI to use             (safety.py)
  3. build the instructions: static prompt + per-request context   (prompts.py, context.py)
  4. replay recent history and ask Gemini                          (memory.py)
  5. run any tool calls the model asks for, as THIS user only      (tools.py)
  6. return the text, plus any changes waiting for confirmation    (actions.py)

Gemini is reached through GeminiBackend, the only code that imports the google-genai SDK.
Tests (and any other provider) can pass a different `backend=` object with the same
`generate()` method. The API key is read from Django settings on the server and is never sent
to the browser or logged.

Settings (all optional except the key):
    GEMINI_API_KEY            required; load it from an environment variable
    GEMINI_MODEL              default "gemini-2.5-flash"; check Google's docs for current model names
    GEMINI_TIMEOUT_SECONDS    default 30
    AI_MAX_OUTPUT_TOKENS      default 2048
    AI_TEMPERATURE            default 0.4
"""

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings

from . import memory, safety, tools
from .context import build_request_context, build_system_instruction
from .prompts import get_system_prompt

import os
from dotenv import load_dotenv 

# Load the environment variables 
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")


logger = logging.getLogger(__name__)

MAX_STEPS = 5                   # model calls per user message (the last one is not allowed to use tools)
MAX_TOOL_CALLS = 8              # tool executions per user message

MSG_UNAVAILABLE = "FoodiePlug AI isn't available right now. Please try again in a little while."
MSG_NOT_CONFIGURED = "FoodiePlug AI isn't set up yet. Please try again later."
MSG_BLOCKED = ("I can't help with that request, but I'm happy to help with meals, "
               "your pantry, shopping lists or your food budget.")
MSG_LOOP = "I couldn't finish looking that up. Please try asking in a simpler way."
MSG_SIGN_IN = "Please sign in to use FoodiePlug AI."

MSG_QUOTA_EXCEEDED = (
    "FoodiePlug AI has reached its current usage limit. "
    "Please try again after the quota resets. "
    "Your FoodiePlug data hasn't been changed."
)


# =========================================================
# BACKEND CONTRACT
# =========================================================

class AIBackendError(Exception):
    """The model provider failed. The text is for logs, never shown to the user."""


class AIBackendNotConfigured(AIBackendError):
    """No API key is configured."""


class AIBackendQuotaExceeded(AIBackendError):
    """The provider's request quota has been exhausted."""



@dataclass
class ToolCall:
    name: str
    args: dict


@dataclass
class ModelTurn:
    text: str = ""
    tool_calls: list = field(default_factory=list)
    raw: Any = None                 # provider-native content, replayed untouched within one answer
    blocked: bool = False           # the provider returned nothing usable (e.g. a safety block)



def _setting(name, default):
    value = getattr(settings, name, None)

    if value not in (None, ""):
        return value

    return os.getenv(name, default)


# =========================================================
# GEMINI
# =========================================================

class GeminiBackend:
    """Thin adapter around the google-genai SDK."""

    def __init__(self, api_key=None, model=None):
        self._api_key = api_key
        self._model = model
        self._client = None
    
    
    @property
    def api_key(self):
        return (
            self._api_key
            or _setting("GEMINI_API_KEY", "")
        )


        
    @property
    def model(self):
        return self._model or _setting(
            "GEMINI_MODEL",
            "gemini-3.8-flash",
        )


    def _get_client(self):
        if not self.api_key:
            raise AIBackendNotConfigured("GEMINI_API_KEY is not set.")
        if self._client is None:
            try:
                genai = importlib.import_module("google.genai")
                types = importlib.import_module("google.genai.types")
            except ImportError as error:
                raise AIBackendNotConfigured("The google-genai package is not installed.") from error

            timeout_ms = int(float(_setting("GEMINI_TIMEOUT_SECONDS", 30)) * 1000)
            self._client = genai.Client(api_key=self.api_key,
                                        http_options=types.HttpOptions(timeout=timeout_ms))
        return self._client

    def generate(self, *, system_instruction, entries, tool_declarations):
        client = self._get_client()
        types = importlib.import_module("google.genai.types")

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=float(_setting("AI_TEMPERATURE", 0.4)),
            max_output_tokens=int(_setting("AI_MAX_OUTPUT_TOKENS", 2048)),
            tools=[types.Tool(function_declarations=tool_declarations)] if tool_declarations else None,
            # We run the tool loop ourselves so every call is permission-checked and logged.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        try:
            # Try the primary model, then an optional fallback for
            # temporary availability failures or model-specific quota limits.
            primary_model = self.model
            fallback_model = str(
                _setting("GEMINI_FALLBACK_MODEL", "gemini-3.6-flash")
            ).strip()

            models_to_try = [primary_model]

            if fallback_model and fallback_model != primary_model:
                models_to_try.append(fallback_model)

            response = None
            last_error = None

            for index, model_name in enumerate(models_to_try):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=self._to_contents(entries, types),
                        config=config,
                    )
                    break

                except Exception as error:
                    last_error = error

                    status_code = None
                    for candidate in (
                        getattr(error, "code", None),
                        getattr(error, "status_code", None),
                        getattr(
                            getattr(error, "response", None),
                            "status_code",
                            None,
                        ),
                    ):
                        try:
                            status_code = int(candidate)
                        except (TypeError, ValueError):
                            continue
                        if status_code:
                            break
                        status_code = None

                    error_details = str(error).upper()

                    is_quota_error = (
                        status_code == 429
                        or "RESOURCE_EXHAUSTED" in error_details
                    )

                    is_server_error = (
                        status_code is not None
                        and 500 <= status_code < 600
                    )
                    is_unavailable = (
                        is_server_error
                        or "UNAVAILABLE" in error_details
                    )

                    has_fallback = index < len(models_to_try) - 1

                    # Do not retry arbitrary errors with another model.
                    if has_fallback and (
                        is_quota_error or is_unavailable
                    ):
                        logger.warning(
                            "Gemini model %s failed with status %s. "
                            "Trying configured fallback model.",
                            model_name,
                            status_code or type(error).__name__,
                        )
                        continue

                    if is_quota_error:
                        logger.warning(
                            "Gemini quota exhausted for model %s.",
                            model_name,
                        )
                        raise AIBackendQuotaExceeded(
                            "Gemini request quota exhausted."
                        ) from error

                    logger.error(
                        "Gemini request failed for model %s (%s).",
                        model_name,
                        type(error).__name__,
                    )
                    raise AIBackendError(
                        type(error).__name__
                    ) from error

            if response is None:
                # Defensive guard; normally the final exception is raised above.
                raise AIBackendError(
                    type(last_error).__name__ if last_error else
                    "No Gemini response received."
                ) from last_error

            return self._parse_response(response)
        except (AIBackendError, AIBackendQuotaExceeded):
            raise

    @staticmethod
    def _to_contents(entries, types):
        """Neutral entries -> Gemini Content objects."""
        contents = []
        for entry in entries:
            role = entry["role"]
            if role in ("user", "model") and "text" in entry:
                contents.append(types.Content(role=role, parts=[types.Part(text=entry["text"])]))
            elif role == "model" and "raw" in entry:
                contents.append(entry["raw"])           # as returned, so any thought signatures survive
            elif role == "tool":
                parts = [types.Part.from_function_response(name=r["name"], response=r["response"])
                         for r in entry["results"]]
                contents.append(types.Content(role="user", parts=parts))
        return contents

    
    @staticmethod
    def _parse_response(response):
        candidates = getattr(response, "candidates", None) or []

        if not candidates:
            return ModelTurn(blocked=True)

        content = getattr(candidates[0], "content", None)
        parts = getattr(content, "parts", None) or []

        if not parts:
            return ModelTurn(blocked=True)

        text_parts = []
        calls = []

        for part in parts:
            function_call = getattr(part, "function_call", None)

            if function_call is not None:
                name = getattr(function_call, "name", None)
                args = getattr(function_call, "args", None)

                if name:
                    if not isinstance(args, dict):
                        args = dict(args or {})

                    calls.append(ToolCall(name=name, args=args))

            elif (
                getattr(part, "text", None)
                and not getattr(part, "thought", False)
            ):
                text_parts.append(part.text)

        text = "".join(text_parts).strip()

        if not calls and not text:
            return ModelTurn(blocked=True)

        return ModelTurn(
            text=text,
            tool_calls=calls,
            raw=content,
        )


# =========================================================
# AGENT
# =========================================================

@dataclass
class AgentReply:
    text: str
    conversation_id: str
    pending_actions: list = field(default_factory=list)    # changes waiting for the user's Confirm
    tools_used: list = field(default_factory=list)
    ok: bool = True
    error_code: str = ""



class FoodiePlugAgent:
    def __init__(self, backend=None, store=None, max_steps=MAX_STEPS):
        # An explicitly injected backend is retained for tests.
        # Normal requests select a backend using the current user's settings.
        self._injected_backend = backend
        self.store = store or memory.DatabaseConversationStore()
        self.max_steps = max(1, int(max_steps))

    def _backend_for_user(self, user):
        """Build a Gemini backend using only this user's saved credentials."""
        from apps.ai.models import UserAIConfig
        from .credentials import (
            CredentialEncryptionError,
            decrypt_api_key,
        )

        config = UserAIConfig.objects.filter(user=user).first()

        if not config or not config.encrypted_api_key:
            raise AIBackendNotConfigured(
                "This user has not configured a Gemini API key."
            )

        try:
            api_key = decrypt_api_key(config.encrypted_api_key)
        except CredentialEncryptionError as exc:
            raise AIBackendNotConfigured(
                "The user's Gemini credentials could not be loaded."
            ) from exc

        if not api_key:
            raise AIBackendNotConfigured(
                "This user has not configured a Gemini API key."
            )

        return GeminiBackend(
            api_key=api_key,
            model=config.model_name,
        )


    def respond(self, user, message, conversation_id=None):
        conv_id = conversation_id if memory.is_valid_conversation_id(conversation_id) else memory.new_conversation_id()

        def fail(text, code):
            return AgentReply(text=text, conversation_id=conv_id, ok=False, error_code=code)

        if user is None or not getattr(user, "is_authenticated", False):
            return fail(MSG_SIGN_IN, "not_authenticated")

        # 1. validate + rate limit
        try:
            cleaned = safety.validate_user_message(message)
            safety.check_rate_limit(user.pk)
        except safety.SafetyError as error:
            return fail(error.message, error.code)

        # 2. what this user allows the AI to use
        permissions = safety.get_permissions(user)

        # 3. instructions
        flagged = safety.looks_like_prompt_injection(cleaned)
        if flagged:
            logger.warning("AI: possible prompt-injection attempt (user=%s)", user.pk)

        system_instruction = build_system_instruction(
            get_system_prompt(),
            build_request_context(user, permissions, injection_flagged=flagged),
        )
        declarations = tools.get_tool_declarations(permissions)

        # 4. conversation so far + the new message
        entries = memory.recent_history(self.store, user, conv_id)
        entries.append({"role": "user", "text": cleaned})

        pending, used, calls_made = [], [], 0

        try:
            backend = self._injected_backend or self._backend_for_user(user)
            for step in range(self.max_steps):
                last_step = step == self.max_steps - 1
                turn = backend.generate(
                    system_instruction=system_instruction,
                    entries=entries,
                    tool_declarations=[] if last_step else declarations,     # force an answer at the end
                )

                if turn.blocked:
                    return fail(MSG_BLOCKED, "blocked")

                if not turn.tool_calls:
                    text = safety.finalize_reply(turn.text)
                    self._remember(user, conv_id, cleaned, text)
                    return AgentReply(text=text, conversation_id=conv_id, pending_actions=pending,
                                      tools_used=used)

                if last_step:
                    return fail(MSG_LOOP, "tool_loop_limit")

                # 5. run the requested tools, as this user, under their permissions
                entries.append({"role": "model", "raw": turn.raw})
                results = []
                for call in turn.tool_calls:
                    if calls_made >= MAX_TOOL_CALLS:
                        result = {"ok": False,
                                  "error": "Too many lookups for one answer. Answer with what you already have."}
                    else:
                        calls_made += 1
                        result = tools.dispatch(user, call.name, call.args, permissions)
                        if call.name not in used:
                            used.append(call.name)

                    if result.get("ok"):
                        action = (result.get("data") or {}).get("pending_action")
                        if isinstance(action, dict) and action.get("id"):
                            pending.append(action)

                    results.append({"name": call.name, "response": result})

                entries.append({"role": "tool", "results": results})

            return fail(MSG_LOOP, "tool_loop_limit")

        
        except AIBackendNotConfigured:
            logger.error(
                "AI is not configured (missing GEMINI_API_KEY or google-genai package)."
            )
            return fail(MSG_NOT_CONFIGURED, "not_configured")
        except AIBackendQuotaExceeded:
            return fail(MSG_QUOTA_EXCEEDED, "quota_exceeded")
        except AIBackendError as error:
            logger.error("AI provider error: %s", error)
            return fail(MSG_UNAVAILABLE, "provider_error")
        except Exception:
            logger.exception("AI agent failed unexpectedly")
            return fail(MSG_UNAVAILABLE, "internal_error")


    def _remember(self, user, conversation_id, user_text, reply_text):
        try:
            self.store.append_turn(user, conversation_id, user_text, reply_text)
        except Exception:
            logger.exception("AI history could not be saved")      # the reply is still delivered


_agent = None


def get_agent():
    """Shared agent for views."""
    global _agent
    if _agent is None:
        _agent = FoodiePlugAgent()
    return _agent