
"""
apps/ai/services/memory.py

Persistent, user-scoped FoodiePlug AI conversation history.
"""

import re
import uuid

from django.db import transaction
from django.utils import timezone

from apps.ai.models import AIConversation, AIMessage

_CONVERSATION_ID = re.compile(r"^[0-9a-f]{32}$")

HISTORY_FOR_MODEL = 12
MAX_STORED_MESSAGES = 40
MAX_CONVERSATIONS = 30
MAX_TITLE_CHARS = 60


def is_valid_conversation_id(value):
    return isinstance(value, str) and bool(
        _CONVERSATION_ID.fullmatch(value)
    )


def new_conversation_id():
    return uuid.uuid4().hex


class ConversationStore:
    """Interface used by the AI agent."""

    def get_messages(self, user, conversation_id):
        raise NotImplementedError

    def append_turn(self, user, conversation_id, user_text, assistant_text):
        raise NotImplementedError

    def list_conversations(self, user):
        raise NotImplementedError

    def delete(self, user, conversation_id):
        raise NotImplementedError

    def clear_all(self, user):
        raise NotImplementedError


class DatabaseConversationStore(ConversationStore):
    """Persistent conversation storage isolated by authenticated user."""

    def get_messages(self, user, conversation_id):
        if not is_valid_conversation_id(conversation_id):
            return []

        conversation = AIConversation.objects.filter(
            id=conversation_id,
            user=user,
        ).first()

        if conversation is None:
            return []

        messages = conversation.messages.order_by(
            "-created_at", "-pk"
        )[:MAX_STORED_MESSAGES]

        return [
            {
                "role": message.role,
                "text": message.content,
                "at": message.created_at.isoformat(),
            }
            for message in reversed(list(messages))
        ]

    def list_conversations(self, user):
        conversations = AIConversation.objects.filter(
            user=user
        ).order_by("-updated_at")[:MAX_CONVERSATIONS]

        return [
            {
                "id": conversation.id,
                "title": conversation.title,
                "updated_at": conversation.updated_at.isoformat(),
            }
            for conversation in conversations
        ]

    @transaction.atomic
    def append_turn(self, user, conversation_id, user_text, assistant_text):
        if not is_valid_conversation_id(conversation_id):
            raise ValueError("Invalid conversation ID.")

        conversation = AIConversation.objects.filter(
            id=conversation_id,
            user=user,
        ).first()

        if conversation is None:
            conversation = AIConversation.objects.create(
                id=conversation_id,
                user=user,
                title=self._title(user_text),
            )

        now = timezone.now()

        AIMessage.objects.bulk_create([
            AIMessage(
                conversation=conversation,
                role=AIMessage.Role.USER,
                content=user_text,
                created_at=now,
            ),
            AIMessage(
                conversation=conversation,
                role=AIMessage.Role.MODEL,
                content=assistant_text,
                created_at=now,
            ),
        ])

        # Keep only the newest 40 messages per conversation.
        old_message_ids = list(
            conversation.messages.order_by(
                "-created_at", "-pk"
            ).values_list("pk", flat=True)[MAX_STORED_MESSAGES:]
        )

        if old_message_ids:
            conversation.messages.filter(
                pk__in=old_message_ids
            ).delete()

        conversation.updated_at = now
        conversation.save(update_fields=["updated_at"])

        # Enforce the per-user conversation limit.
        excess_ids = list(
            AIConversation.objects.filter(user=user)
            .order_by("-updated_at")
            .values_list("id", flat=True)[MAX_CONVERSATIONS:]
        )

        if excess_ids:
            AIConversation.objects.filter(
                user=user,
                id__in=excess_ids,
            ).delete()

    def rename(self, user, conversation_id, title):
        if not is_valid_conversation_id(conversation_id):
            return False

        updated = AIConversation.objects.filter(
            id=conversation_id,
            user=user,
        ).update(title=title, updated_at=timezone.now())

        return updated > 0

    def delete(self, user, conversation_id):
        if not is_valid_conversation_id(conversation_id):
            return False

        deleted, _ = AIConversation.objects.filter(
            id=conversation_id,
            user=user,
        ).delete()

        return deleted > 0

    def clear_all(self, user):
        count = AIConversation.objects.filter(user=user).count()
        AIConversation.objects.filter(user=user).delete()
        return count

    @staticmethod
    def _title(text):
        text = " ".join((text or "").split())
        if len(text) <= MAX_TITLE_CHARS:
            return text
        return text[:MAX_TITLE_CHARS - 1] + "…"



def recent_history(
    store,
    user,
    conversation_id,
    limit=HISTORY_FOR_MODEL,
):
    """Return recent messages in the format expected by the AI backend."""
    messages = store.get_messages(user, conversation_id)

    return [
        {
            "role": message["role"],
            "text": message["text"],
        }
        for message in messages[-limit:]
        if message.get("role") in ("user", "model")
        and message.get("text")
    ]
