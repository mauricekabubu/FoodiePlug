import re
from smtplib import SMTPException
from urllib.parse import urlsplit

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from unittest import mock

from .models import PasswordResetAttempt


class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="reset-user",
            email="reset-user@example.com",
            password="Existing-safe-password-453!",
            first_name="Amina",
        )
        self.request_url = reverse("forgot_password")

    def test_forgot_password_renders_email_form_and_csrf(self):
        response = self.client.get(self.request_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="email"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertContains(response, "Forgot your password?")

    def test_invalid_email_is_reported_on_the_form(self):
        response = self.client.post(
            self.request_url,
            {"email": "not-an-email"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertEqual(mail.outbox, [])

    @override_settings(SITE_URL="https://foodieplug.example")
    def test_reset_email_has_absolute_https_url_and_single_line_subject(self):
        response = self.client.post(
            self.request_url,
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.subject, "Reset your FoodiePlug password")
        self.assertNotIn("\n", message.subject)
        self.assertEqual(message.to, [self.user.email])
        self.assertIn("within one hour", message.body)

        match = re.search(r"https://foodieplug\.example/reset/\S+", message.body)
        self.assertIsNotNone(match)
        reset_url = urlsplit(match.group(0))
        self.assertEqual(reset_url.scheme, "https")
        self.assertEqual(reset_url.netloc, "foodieplug.example")
        self.assertRegex(reset_url.path, r"^/reset/[^/]+/[^/]+/$")

        html_message = message.alternatives[0][0]
        self.assertIn("Reset password", html_message)
        self.assertIn(match.group(0), html_message)

    def test_unknown_email_has_same_confirmation_without_sending_email(self):
        known = self.client.post(
            self.request_url,
            {"email": self.user.email},
            follow=True,
        )
        unknown = self.client.post(
            self.request_url,
            {"email": "nobody@example.com"},
            follow=True,
        )

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.content, unknown.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(unknown, "If an eligible account matches")

    @override_settings(
        SITE_URL="https://foodieplug.example",
        ALLOWED_HOSTS=["*"],
    )
    def test_reset_email_uses_configured_site_not_request_host(self):
        self.client.post(
            self.request_url,
            {"email": self.user.email},
            HTTP_HOST="attacker.example",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("https://foodieplug.example/reset/", mail.outbox[0].body)
        self.assertNotIn("attacker.example", mail.outbox[0].body)

    def test_social_only_user_does_not_receive_reset_email(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])

        response = self.client.post(self.request_url, {"email": self.user.email})

        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(mail.outbox, [])

    @override_settings(SITE_URL="http://localhost:8000")
    def test_password_reset_changes_password_and_token_cannot_be_reused(self):
        self.client.post(self.request_url, {"email": self.user.email})
        reset_url = re.search(
            r"http://localhost:8000/reset/\S+",
            mail.outbox[0].body,
        ).group(0)
        reset_path = urlsplit(reset_url).path
        landing = self.client.get(reset_path)
        self.assertEqual(landing.status_code, 302)

        form_url = landing["Location"]
        form = self.client.get(form_url)
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, "Choose a new password.")

        response = self.client.post(
            form_url,
            {
                "new_password1": "Brand-new-safe-password-837!",
                "new_password2": "Brand-new-safe-password-837!",
            },
        )

        self.assertRedirects(response, reverse("password_reset_complete"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Brand-new-safe-password-837!"))
        self.assertTrue(
            self.client.login(
                username=self.user.username,
                password="Brand-new-safe-password-837!",
            )
        )

        reused = self.client.get(reset_path)
        self.assertEqual(reused.status_code, 200)
        self.assertContains(reused, "This reset link can’t be used.")

    def test_invalid_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        response = self.client.get(
            reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uid, "token": "invalid-token"},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This reset link can’t be used.")

    @override_settings(PASSWORD_RESET_TIMEOUT=-1)
    def test_expired_token_is_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        response = self.client.get(
            reverse(
                "password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This reset link can’t be used.")

    def test_password_mismatch_and_validation_errors_are_shown(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse(
            "password_reset_confirm",
            kwargs={"uidb64": uid, "token": token},
        )
        response = self.client.get(url)
        form_url = response["Location"]
        self.client.get(form_url)

        mismatch = self.client.post(
            form_url,
            {
                "new_password1": "Brand-new-safe-password-837!",
                "new_password2": "A-different-password-837!",
            },
        )
        self.assertEqual(mismatch.status_code, 200)
        self.assertContains(mismatch, "The two password fields didn’t match.")

        weak = self.client.post(
            form_url,
            {"new_password1": "123", "new_password2": "123"},
        )
        self.assertEqual(weak.status_code, 200)
        self.assertContains(weak, "This password is too short.")

    def test_email_delivery_failure_still_shows_generic_confirmation(self):
        with mock.patch(
            "django.core.mail.EmailMessage.send",
            side_effect=SMTPException("private SMTP diagnostic"),
        ):
            response = self.client.post(
                self.request_url,
                {"email": self.user.email},
                follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "If an eligible account matches")
        self.assertNotContains(response, "private SMTP diagnostic")

    def test_reset_requests_are_limited_per_ip_and_email(self):
        for _ in range(4):
            response = self.client.post(
                self.request_url,
                {"email": self.user.email},
            )
            self.assertRedirects(response, reverse("password_reset_done"))

        self.assertEqual(len(mail.outbox), 3)
        self.assertGreaterEqual(PasswordResetAttempt.objects.count(), 2)

    @override_settings(SITE_URL="http://attacker.example")
    def test_non_https_public_reset_origin_does_not_generate_email(self):
        with self.assertRaises(ImproperlyConfigured):
            self.client.post(
                self.request_url,
                {"email": self.user.email},
            )

        self.assertEqual(mail.outbox, [])
