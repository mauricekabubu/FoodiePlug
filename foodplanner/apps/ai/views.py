"""
apps/ai/views.py

HTTP endpoints for the FoodiePlug AI Assistant.

Responsibilities:
- Render the AI page.
- Receive chat messages and return JSON.
- Load, rename, and delete the authenticated user's conversations.
- Confirm a pending AI action only after an explicit user request.
- Enforce authentication, CSRF, input validation, and conversation ownership.
"""

import json
import logging
import re

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .services.agent import get_agent
from .services.actions import confirm_action
from .services.memory import recent_history
from .services.safety import (
    SafetyError,
    get_permissions,
    validate_user_message,
)

logger = logging.getLogger(__name__)

CONVERSATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_JSON_BODY = 16_384
MAX_TITLE_LENGTH = 120

# How many messages the page may load when re-opening a conversation.
# (This is for display; it is independent of how much history the agent sends to the model.)
DISPLAY_HISTORY_LIMIT = 200


def _json_body(request):
    """Decode a bounded JSON request body into a dictionary."""
    if len(request.body) > MAX_JSON_BODY:
        raise ValueError("Request body is too large.")

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON request body.") from exc

    if not isinstance(payload, dict):
        raise ValueError("The request body must be a JSON object.")

    return payload


def _error(message, status=400, code="invalid_request"):
    return JsonResponse(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
            },
        },
        status=status,
    )


def _conversation_id(value, required=False):
    """Validate the opaque UUID-hex conversation IDs used by memory.py."""
    if value in (None, "") and not required:
        return None

    if not isinstance(value, str) or not CONVERSATION_ID_RE.fullmatch(value):
        raise ValueError("Invalid conversation ID.")

    return value


def _get_store(agent):
    """
    Locate the store used by the agent.

    Keep the agent and views on the same store instance so conversation
    history is consistent between chat requests and history operations.
    """
    store = getattr(agent, "store", None)
    if store is None:
        store = getattr(agent, "conversation_store", None)

    if store is None:
        raise RuntimeError(
            "The AI agent has no conversation store configured. "
            "Expose its ConversationStore instance as agent.store."
        )

    return store


def _owned_conversations(store, user):
    """
    Return {conversation_id: title} for conversations that belong to `user`.

    The store lists only the given user's conversations, so membership in this
    mapping is the ownership check.
    """
    owned = {}

    for entry in (store.list_conversations(user) or []):
        if not isinstance(entry, dict):
            continue

        conversation_id = entry.get("id") or entry.get("conversation_id")
        if not isinstance(conversation_id, str):
            continue
        if not CONVERSATION_ID_RE.fullmatch(conversation_id):
            continue

        owned[conversation_id] = str(entry.get("title") or "New conversation")[:MAX_TITLE_LENGTH]

    return owned


def _history_for_template(store, user):
    """Build the grouped history structure used by the AI page template."""
    conversations = store.list_conversations(user) or []
    items = []

    for entry in conversations:
        if not isinstance(entry, dict):
            continue

        conversation_id = entry.get("id") or entry.get("conversation_id")
        if not isinstance(conversation_id, str):
            continue
        if not CONVERSATION_ID_RE.fullmatch(conversation_id):
            continue

        title = str(entry.get("title") or "New conversation")[:MAX_TITLE_LENGTH]
        items.append({
            "id": conversation_id,
            "title": title,
            "updated_at": entry.get("updated_at"),
        })

    # Cache indexes can have varying timestamp formats. Avoid unsafe or
    # unreliable sorting here; the store's order is retained.
    return [{"label": "Recent", "items": items}] if items else []


def _public_role(role):
    """Map stored roles (Gemini uses 'model') to the two roles the page understands."""
    role = str(role or "").lower()

    if role in ("user", "human"):
        return "user"
    if role in ("model", "assistant", "ai"):
        return "assistant"

    return None     # system / tool / unknown messages are never shown


def _message_text(item):
    """Read a stored message's text, tolerating the common key names."""
    for key in ("text", "content", "message"):
        value = item.get(key)
        if isinstance(value, str):
            return value

    return ""


def _source_context(user):
    """Return the server-authoritative availability of each data source."""
    permissions = get_permissions(user)

    definitions = [
        ("foods", "Food Library", "Search the available food library."),
        ("pantry", "Pantry", "Use your saved pantry items."),
        ("meals", "My Meals and Meal Plan", "Use saved meals and scheduled meals."),
        ("shopping", "Shopping Lists", "Read your saved shopping lists."),
        ("budget", "Budget", "Read your food budget and recorded expenses."),
    ]

    sources = []
    for key, label, summary in definitions:
        sources.append({
            "key": key,
            "label": label,
            "summary": summary,
            "available": permissions.allows(key),
        })

    return sources


def _suggested_prompts():
    """Static starter prompts; the AI must still retrieve real data via tools."""
    return [
        {
            "label": "Use what I have",
            "prompt": "What meals can I make with the food in my pantry?",
            "icon": "pantry",
        },
        {
            "label": "Plan my meals",
            "prompt": "Help me plan affordable meals for the next few days.",
            "icon": "calendar",
        },
        {
            "label": "Check my budget",
            "prompt": "Summarize my current food budget and spending.",
            "icon": "budget",
        },
        {
            "label": "Shopping list",
            "prompt": "Help me decide what to add to my shopping list.",
            "icon": "shopping",
        },
    ]


@login_required
@require_GET
def ai_page(request):
    """Render the FoodiePlug AI Assistant page."""
    try:
        agent = get_agent()
        store = _get_store(agent)
        history_groups = _history_for_template(store, request.user)
    except Exception:
        logger.exception("Could not load FoodiePlug AI page data.")
        history_groups = []

    return render(
        request,
        "Ai/assistant.html",
        {
            "suggested_prompts": _suggested_prompts(),
            "sources": _source_context(request.user),
            "conversation_groups": history_groups,
        },
    )


@login_required
@require_POST
def chat(request):
    """Send one message to the AI agent."""
    try:
        payload = _json_body(request)
        message = validate_user_message(payload.get("message", ""))
        conversation_id = _conversation_id(payload.get("conversation_id"))
    except SafetyError as exc:
        return _error(str(exc), 400, getattr(exc, "code", "invalid_message"))
    except ValueError as exc:
        return _error(str(exc), 400)

    # The browser's context.sources value is intentionally not used to grant
    # permissions. get_permissions() and tool dispatch enforce access server-side.
    try:
        reply = get_agent().respond(
            request.user,
            message,
            conversation_id=conversation_id,
        )
    except SafetyError as exc:
        status = 429 if getattr(exc, "code", "") == "rate_limit" else 400
        return _error(str(exc), status, getattr(exc, "code", "safety_error"))
    except Exception:
        logger.exception("FoodiePlug AI chat request failed.")
        return _error(
            "FoodiePlug AI could not process that request right now.",
            503,
            "ai_unavailable",
        )

    if not getattr(reply, "ok", False):
        code = getattr(reply, "error_code", None) or "ai_error"
        status = 429 if code == "rate_limit" else 503
        return _error(
            getattr(reply, "text", None) or "FoodiePlug AI could not answer right now.",
            status,
            code,
        )

    # Keep this response shape aligned with static/js/ai.js.
    # Pending actions are not executed by this endpoint.
    return JsonResponse({
        "ok": True,
        "response": str(getattr(reply, "text", "") or ""),
        "conversation_id": getattr(reply, "conversation_id", None),
        "conversation_title": message[:60],
        "pending_actions": getattr(reply, "pending_actions", []),
        "tools_used": getattr(reply, "tools_used", []),
    })


@login_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def conversation_detail(request, conversation_id):
    """Read, rename, or delete a conversation belonging to the current user."""
    try:
        conversation_id = _conversation_id(conversation_id, required=True)
        agent = get_agent()
        store = _get_store(agent)
    except ValueError as exc:
        return _error(str(exc), 400)
    except Exception:
        logger.exception("Could not access the AI conversation store.")
        return _error("Conversation storage is unavailable.", 503, "storage_unavailable")

    if request.method == "GET":
        # 1) Ownership first. The store only lists this user's conversations, so a
        #    conversation that is missing or belongs to someone else gets the same 404.
        try:
            owned = _owned_conversations(store, request.user)
        except Exception:
            logger.exception("Could not verify AI conversation ownership.")
            return _error("Could not verify this conversation.", 503, "storage_error")

        if conversation_id not in owned:
            return _error("Conversation not found.", 404, "not_found")

        # 2) Then load the messages.
        try:
            history = recent_history(
                store,
                request.user,
                conversation_id,
                limit=DISPLAY_HISTORY_LIMIT,
            )
        except Exception:
            logger.exception("Could not load AI conversation.")
            return _error("Could not load this conversation.", 503, "storage_error")

        messages = []
        for item in (history or []):
            if not isinstance(item, dict):
                continue

            role = _public_role(item.get("role"))
            if role is None:
                continue

            messages.append({"role": role, "content": _message_text(item)})

        if not messages:
            # Listed in the user's index but nothing readable came back: usually expired
            # cache entries or a role/key naming mismatch in the store.
            logger.warning(
                "AI conversation %s is listed for user %s but returned no readable messages.",
                conversation_id,
                request.user.pk,
            )

        return JsonResponse({
            "ok": True,
            "id": conversation_id,
            "title": owned[conversation_id],
            "messages": messages,
        })

    if request.method == "PATCH":
        try:
            payload = _json_body(request)
        except ValueError as exc:
            return _error(str(exc), 400)

        title = payload.get("title")
        if not isinstance(title, str):
            return _error("A conversation title is required.")

        title = " ".join(title.split()).strip()
        if not title:
            return _error("A conversation title cannot be empty.")
        if len(title) > MAX_TITLE_LENGTH:
            return _error(
                f"Conversation titles must be {MAX_TITLE_LENGTH} characters or fewer."
            )

        # The current cache store derives titles from the first user message
        # and does not expose a rename method. Don't report a rename as saved
        # until the store implements a user-scoped rename operation.
        rename = getattr(store, "rename", None)
        if not callable(rename):
            return _error(
                "Conversation renaming is not implemented in the conversation store yet.",
                501,
                "not_implemented",
            )

        try:
            renamed = rename(request.user, conversation_id, title)
        except Exception:
            logger.exception("Could not rename AI conversation.")
            return _error("Could not rename this conversation.", 503, "storage_error")

        if not renamed:
            return _error("Conversation not found.", 404, "not_found")

        return JsonResponse({"ok": True, "id": conversation_id, "title": title})

    # DELETE
    try:
        deleted = store.delete(request.user, conversation_id)
    except Exception:
        logger.exception("Could not delete AI conversation.")
        return _error("Could not delete this conversation.", 503, "storage_error")

    if not deleted:
        return _error("Conversation not found.", 404, "not_found")

    return JsonResponse({"ok": True, "deleted": True})


@login_required
@require_POST
def confirm_pending_action(request):
    """
    Confirm one pending action.

    The browser must send the pending action ID after a clear user confirmation.
    The action service must independently verify ownership and validate the
    stored payload before making any changes.
    """
    try:
        payload = _json_body(request)
    except ValueError as exc:
        return _error(str(exc), 400)

    action_id = payload.get("action_id")
    if not isinstance(action_id, str) or not action_id or len(action_id) > 64:
        return _error("A valid pending action ID is required.")

    try:
        result = confirm_action(request.user, action_id)
    except Exception:
        logger.exception("Pending AI action confirmation failed.")
        return _error("The action could not be confirmed.", 503, "action_error")

    return JsonResponse(
        {
            "ok": bool(getattr(result, "ok", False)),
            "message": str(getattr(result, "message", "") or ""),
            "details": getattr(result, "details", None),
        },
        status=200 if getattr(result, "ok", False) else 400,
    )