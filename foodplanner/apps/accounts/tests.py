from django.contrib.auth import get_user_model
from django.contrib import messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import TestCase, override_settings
from django.test import RequestFactory
from django.urls import reverse

from apps.ai.models import UserAIConfig
from .models import Profile
from .views import dashboard


class GoogleOAuthTests(TestCase):
    @override_settings(
        SOCIALACCOUNT_PROVIDERS={
            "google": {
                "APP": {
                    "client_id": "test-client-id",
                    "secret": "test-client-secret",
                    "key": "",
                },
                "SCOPE": ["profile", "email"],
            }
        }
    )
    def test_google_login_post_starts_provider_flow(self):
        response = self.client.post(reverse("google_login"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response["Location"].startswith("https://accounts.google.com/")
        )

    def test_login_and_registration_render_csrf_protected_google_forms(self):
        for page_name in ("login", "register"):
            with self.subTest(page=page_name):
                response = self.client.get(reverse(page_name))

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'method="post"')
                self.assertContains(response, 'action="/accounts/google/login/"')
                self.assertContains(response, 'name="csrfmiddlewaretoken"')


class UserProfileSignalTests(TestCase):
    def test_password_login_redirects_to_dashboard(self):
        get_user_model().objects.create_user(
            username="password-user",
            email="password@example.com",
            password="a-safe-test-password",
        )

        response = self.client.post(
            reverse("login"),
            {
                "username": "password-user",
                "password": "a-safe-test-password",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )

    def test_new_user_gets_profile_with_valid_defaults(self):
        user = get_user_model().objects.create_user(
            username="google-user",
            email="google@example.com",
            password="a-safe-test-password",
            first_name="Google",
            last_name="User",
        )

        profile = Profile.objects.get(user=user)
        self.assertEqual(profile.display_name, "Google User")
        self.assertEqual(profile.preferred_language, Profile.LanguageChoices.KENYAN_MIX)
        self.assertEqual(profile.slang_level, Profile.SlangLevels.MEDIUM)
        self.assertEqual(profile.timezone, "Africa/Nairobi")

    def test_profile_creation_is_idempotent(self):
        user = get_user_model().objects.create_user(
            username="existing-profile-user",
            email="existing@example.com",
            password="a-safe-test-password",
        )

        from django.db.models.signals import post_save

        post_save.send(
            sender=get_user_model(),
            instance=user,
            created=True,
        )

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_password_registration_creates_profile_and_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("register"),
            {
                "fullname": "Foodie User",
                "username": "foodie-user",
                "email": "foodie@example.com",
                "password": "a-safe-test-password",
                "confirm_password": "a-safe-test-password",
                "terms": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("dashboard"),
            fetch_redirect_response=False,
        )
        user = get_user_model().objects.get(username="foodie-user")
        self.assertTrue(Profile.objects.filter(user=user).exists())


class DashboardReminderAndToastTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="dashboard-user",
            email="dashboard@example.com",
            password="a-safe-test-password",
            first_name="Dashboard",
        )

    def test_dashboard_reminds_users_without_a_saved_key(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="ai-key-reminder"')
        self.assertContains(response, 'href="/settings/#ai"')

    def test_dashboard_hides_reminder_when_user_key_is_configured(self):
        UserAIConfig.objects.create(
            user=self.user,
            encrypted_api_key="encrypted-test-value",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard"))

        self.assertNotContains(response, 'id="ai-key-reminder"')

    def test_reminder_dismissal_is_saved_for_the_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("gemini_reminder_dismiss"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"dismissed": True})
        self.assertNotContains(self.client.get(reverse("dashboard")), 'id="ai-key-reminder"')

    def test_anonymous_users_are_redirected_from_dashboard(self):
        response = self.client.get(reverse("dashboard"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('dashboard')}",
        )

    def test_dashboard_renders_each_django_message_level_once(self):
        request = RequestFactory().get(reverse("dashboard"))
        request.user = self.user
        request.session = {}
        request._messages = FallbackStorage(request)
        messages.success(request, "Success notification.")
        messages.error(request, "Error notification.")
        messages.warning(request, "Warning notification.")
        messages.info(request, "Information notification.")

        response = dashboard(request)
        content = response.content.decode()

        self.assertContains(response, 'id="toast-container"', count=1)
        self.assertContains(response, 'id="flash-messages"', count=1)
        self.assertContains(response, 'data-level="success"')
        self.assertContains(response, 'data-level="error"')
        self.assertContains(response, 'data-level="warning"')
        self.assertContains(response, 'data-level="info"')
        self.assertEqual(content.count('src="/static/js/toasts.js"'), 1)
        self.assertIn("Success notification.", content)
        self.assertIn("Error notification.", content)
        self.assertIn("Warning notification.", content)
        self.assertIn("Information notification.", content)
