from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class InsightsAssistantLinkTests(TestCase):
    def test_authenticated_insights_page_links_to_assistant(self):
        user = get_user_model().objects.create_user(
            username="insights-link-user",
            email="insights-link@example.com",
            password="safe-test-password",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("insights:overview"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["ask_url"], reverse("ai:page"))
