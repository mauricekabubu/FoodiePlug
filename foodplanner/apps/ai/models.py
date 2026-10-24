
"""
apps/ai/models.py

FoodiePlug AI configuration and persistent conversation history.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class UserAIConfig(models.Model):
    """AI provider configuration owned by one authenticated user."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_config",
    )

    # Store encrypted ciphertext here, never plaintext API keys.
    encrypted_api_key = models.TextField(blank=True, default="")

    model_name = models.CharField(
        max_length=100,
        default="gemini-3.8-flash"
    )

    connection_tested_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    connection_test_succeeded = models.BooleanField(default=False)

    # Store only a safe, user-friendly status—not raw provider errors.
    connection_status = models.CharField(
        max_length=30,
        default="untested",
        choices=[
            ("untested", "Not tested"),
            ("success", "Connected"),
            ("failed", "Connection failed"),
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI configuration for user {self.user_id}"

    @property
    def has_api_key(self):
        return bool(self.encrypted_api_key)


def generate_conversation_id():
    return uuid.uuid4().hex

class AIConversation(models.Model):
    """A persistent conversation belonging to one user."""

    id = models.CharField(
        primary_key=True,
        max_length=32,
        default=generate_conversation_id,
        editable=False,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_conversations",
    )

    title = models.CharField(
        max_length=120,
        default="New conversation",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["user", "-updated_at", "-id"]),
        ]

    def __str__(self):
        return self.title


class AIMessage(models.Model):
    """A visible user or assistant message in a conversation."""

    class Role(models.TextChoices):
        USER = "user", "User"
        MODEL = "model", "Assistant"

    conversation = models.ForeignKey(
        AIConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
    )

    content = models.TextField()

    created_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.role} message in {self.conversation_id}"
