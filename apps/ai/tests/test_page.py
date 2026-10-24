from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AssistantPageTests(TestCase):
    def test_authenticated_page_renders_prompt_icons(self):
        user = get_user_model().objects.create_user(
            username="assistant-page-user",
            email="assistant-page@example.com",
            password="safe-test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("ai:page"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Use what I have")
        self.assertContains(response, "<svg", html=False)
