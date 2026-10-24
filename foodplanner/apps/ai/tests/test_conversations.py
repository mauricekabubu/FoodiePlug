"""
apps/ai/tests/test_conversations.py

Targeted tests for the AI conversation endpoint (GET / PATCH / DELETE).

They use a small in-memory fake store and patch `get_agent` and `recent_history`
in apps/ai/views.py, so they check the view's behaviour (ownership, response
shape, error codes) without depending on services/memory.py or Gemini.

Run:  python manage.py test apps.ai.tests.test_conversations
(This file needs apps/ai/tests/__init__.py to exist.)
"""

import json
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .. import views

CONV_A = "a" * 32
CONV_B = "b" * 32
MISSING = "c" * 32


class FakeStore:
    """{user_pk: {conversation_id: {"title": str, "messages": [dict]}}}"""

    def __init__(self):
        self.data = {}

    def add(self, user, conversation_id, title, messages):
        self.data.setdefault(user.pk, {})[conversation_id] = {"title": title, "messages": messages}

    def list_conversations(self, user):
        return [
            {"id": cid, "title": conv["title"]}
            for cid, conv in self.data.get(user.pk, {}).items()
        ]

    def delete(self, user, conversation_id):
        return self.data.get(user.pk, {}).pop(conversation_id, None) is not None

    def rename(self, user, conversation_id, title):
        conv = self.data.get(user.pk, {}).get(conversation_id)
        if conv is None:
            return False
        conv["title"] = title
        return True


class NoRenameStore(FakeStore):
    """A store that does not implement rename (the view must answer 501)."""

    rename = None


def fake_recent_history(store, user, conversation_id, limit=40):
    conv = store.data.get(user.pk, {}).get(conversation_id)
    return list(conv["messages"]) if conv else []


def make_user(name):
    User = get_user_model()
    kwargs = {"password": "pass-12345-word"}
    field = User.USERNAME_FIELD
    kwargs[field] = f"{name}@example.com" if field == "email" else name

    if field != "email" and "email" in [f.name for f in User._meta.get_fields()]:
        kwargs["email"] = f"{name}@example.com"

    return User.objects.create_user(**kwargs)


class ConversationDetailTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice")
        self.bob = make_user("bob")

        self.store = FakeStore()
        self.store.add(self.alice, CONV_A, "Pantry ideas", [
            {"role": "user", "text": "What can I cook with beans?"},
            {"role": "model", "text": "You could make githeri."},
            {"role": "user", "text": "Add maize too."},
            {"role": "model", "text": "Great, githeri with maize."},
        ])
        self.store.add(self.bob, CONV_B, "Bob private chat", [
            {"role": "user", "text": "Bob's secret question"},
            {"role": "model", "text": "Bob's secret answer"},
        ])

        agent = SimpleNamespace(store=self.store)
        patches = [
            mock.patch.object(views, "get_agent", return_value=agent),
            mock.patch.object(views, "recent_history", side_effect=fake_recent_history),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

        self.client.force_login(self.alice)

    def url(self, conversation_id):
        return reverse("ai:conversation_detail", args=[conversation_id])

    # ---------------------------------------------------------------- GET
    def test_returns_ordered_messages_with_expected_shape(self):
        response = self.client.get(self.url(CONV_A))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["id"], CONV_A)
        self.assertEqual(data["title"], "Pantry ideas")
        self.assertEqual(
            [(m["role"], m["content"]) for m in data["messages"]],
            [
                ("user", "What can I cook with beans?"),
                ("assistant", "You could make githeri."),
                ("user", "Add maize too."),
                ("assistant", "Great, githeri with maize."),
            ],
        )

    def test_accepts_assistant_role_and_content_key(self):
        self.store.add(self.alice, CONV_A, "Pantry ideas", [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
            {"role": "system", "content": "never shown"},
        ])

        data = self.client.get(self.url(CONV_A)).json()

        self.assertEqual(
            [(m["role"], m["content"]) for m in data["messages"]],
            [("user", "Hello"), ("assistant", "Hi there")],
        )

    def test_listed_conversation_with_no_messages_returns_empty_list(self):
        self.store.add(self.alice, CONV_A, "Empty", [])

        response = self.client.get(self.url(CONV_A))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["messages"], [])

    def test_unknown_conversation_returns_404(self):
        response = self.client.get(self.url(MISSING))

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "not_found")

    def test_other_users_conversation_returns_404_and_leaks_nothing(self):
        response = self.client.get(self.url(CONV_B))

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("secret", response.content.decode().lower())

    def test_malformed_id_returns_400(self):
        response = self.client.get(self.url("not-a-valid-id"))

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])

    def test_requires_login(self):
        self.client.logout()

        response = self.client.get(self.url(CONV_A))

        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())

    def test_post_is_not_allowed(self):
        response = self.client.post(self.url(CONV_A))

        self.assertEqual(response.status_code, 405)

    # ---------------------------------------------------------------- DELETE
    def test_delete_removes_own_conversation(self):
        response = self.client.delete(self.url(CONV_A))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["deleted"])
        self.assertEqual(self.client.get(self.url(CONV_A)).status_code, 404)

    def test_delete_cannot_remove_another_users_conversation(self):
        response = self.client.delete(self.url(CONV_B))

        self.assertEqual(response.status_code, 404)
        self.assertIn(CONV_B, self.store.data[self.bob.pk])

    # ---------------------------------------------------------------- PATCH
    
    def test_rename_reports_not_implemented_when_store_has_no_rename(self):
        # Replace the normal store with one that does not support renaming.
        store = NoRenameStore()
        store.add(self.alice, CONV_A, "Pantry ideas", [
            {"role": "user", "text": "What can I cook with beans?"},
        ])

        # Update both the agent's store and the history helper's store.
        self.store = store
        views.get_agent.return_value.store = store
        views.recent_history.side_effect = fake_recent_history

        response = self.client.patch(
            self.url(CONV_A),
            data=json.dumps({"title": "New name"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["error"]["code"], "not_implemented")
        self.assertEqual(
            store.data[self.alice.pk][CONV_A]["title"],
            "Pantry ideas",
        )

    def test_rename_rejects_empty_title(self):
        response = self.client.patch(
            self.url(CONV_A),
            data=json.dumps({"title": "   "}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)