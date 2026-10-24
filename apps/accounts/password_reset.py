import hmac
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.views import PasswordResetView
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import PasswordResetAttempt

logger = logging.getLogger(__name__)

RESET_WINDOW_SECONDS = 60 * 60
RESET_LIMIT_PER_EMAIL = 3
RESET_LIMIT_PER_IP = 10


class PasswordResetDeliveryError(Exception):
    def __init__(self, diagnostic_type):
        self.diagnostic_type = diagnostic_type


def _throttle_key(value):
    return salted_hmac(
        "accounts.password_reset.throttle",
        value,
        secret=settings.SECRET_KEY,
        algorithm="sha256",
    ).hexdigest()


def _consume_attempt(value, limit):
    key = _throttle_key(value)
    now = timezone.now()
    with transaction.atomic():
        attempt, created = PasswordResetAttempt.objects.select_for_update().get_or_create(
            key=key,
            defaults={
                "window_started_at": now,
                "attempt_count": 1,
            },
        )
        if created:
            return True

        if (now - attempt.window_started_at).total_seconds() >= RESET_WINDOW_SECONDS:
            attempt.window_started_at = now
            attempt.attempt_count = 1
            attempt.save(update_fields=["window_started_at", "attempt_count"])
            return True

        if attempt.attempt_count >= limit:
            return False

        attempt.attempt_count += 1
        attempt.save(update_fields=["attempt_count"])
        return True


def _trusted_reset_origin():
    site_url = getattr(settings, "SITE_URL", "").strip()
    parsed = urlsplit(site_url)
    hostname = (parsed.hostname or "").lower()
    local_hosts = {"localhost", "127.0.0.1", "::1"}

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or (parsed.scheme == "http" and hostname not in local_hosts)
    ):
        raise ImproperlyConfigured(
            "SITE_URL must be a trusted local HTTP URL or an HTTPS public URL."
        )
    return parsed.netloc, parsed.scheme == "https"


class FoodiePlugPasswordResetForm(PasswordResetForm):
    def send_mail(self, *args, **kwargs):
        try:
            return super().send_mail(*args, **kwargs)
        except Exception as error:
            raise PasswordResetDeliveryError(type(error).__name__) from None

    def save(self, *, request=None, **kwargs):
        email = self.cleaned_data["email"].strip().casefold()
        client_ip = (
            request.META.get("HTTP_X_REAL_IP")
            or request.META.get("REMOTE_ADDR")
            or "unknown"
        )
        if not _consume_attempt(f"ip:{client_ip}", RESET_LIMIT_PER_IP):
            return
        if not _consume_attempt(f"email:{email}", RESET_LIMIT_PER_EMAIL):
            return

        domain, use_https = _trusted_reset_origin()
        kwargs["domain_override"] = domain
        kwargs["use_https"] = use_https
        kwargs["from_email"] = settings.DEFAULT_FROM_EMAIL
        return super().save(request=request, **kwargs)


class SafePasswordResetView(PasswordResetView):
    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except PasswordResetDeliveryError as error:
            logger.error(
                "Password-reset request could not be completed (%s).",
                error.diagnostic_type,
            )
            return HttpResponseRedirect(self.get_success_url())
