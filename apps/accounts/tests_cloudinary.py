from io import BytesIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.accounts.models import Profile
from apps.image_uploads import validate_image_upload
from apps.storage import (
    CloudinaryMediaStorage,
    CloudinaryStorageNotConfigured,
)


def make_png():
    buffer = BytesIO()
    Image.new("RGB", (3, 3), color="green").save(buffer, format="PNG")
    return buffer.getvalue()


def upload_file(content=None, content_type="image/png", name="avatar.png"):
    return SimpleUploadedFile(
        name,
        make_png() if content is None else content,
        content_type=content_type,
    )


class ImageUploadValidationTests(TestCase):
    def test_rejects_disallowed_mime_type(self):
        uploaded = upload_file(content_type="text/plain", name="avatar.txt")

        self.assertEqual(
            validate_image_upload(uploaded),
            "Choose a JPG, PNG or WebP image.",
        )

    def test_rejects_upload_over_five_mib_before_decoding(self):
        uploaded = upload_file(
            content=b"x" * (5 * 1024 * 1024 + 1),
        )

        self.assertEqual(
            validate_image_upload(uploaded),
            "The image must be smaller than 5 MB.",
        )

    def test_rejects_mime_type_that_does_not_match_image_bytes(self):
        uploaded = upload_file(content_type="image/jpeg")

        self.assertEqual(
            validate_image_upload(uploaded),
            "Choose a valid JPG, PNG or WebP image.",
        )

    def test_accepts_valid_png(self):
        self.assertIsNone(validate_image_upload(upload_file()))


class CloudinaryProfileAvatarTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="cloudinary-avatar-user",
            email="cloudinary-avatar@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_profile_form_renders_cloudinary_avatar_url(self):
        profile, _ = Profile.objects.get_or_create(user=self.user)
        profile.avatar.name = (
            "cloudinary/foodieplug/avatars/existing-avatar.png"
        )
        profile.save(update_fields=["avatar"])

        with mock.patch.object(
            CloudinaryMediaStorage,
            "_cloudinary_config",
            return_value=SimpleNamespace(
                cloud_name="foodieplug-test",
                api_key="test-key",
                api_secret="test-secret",
            ),
        ):
            response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "https://res.cloudinary.com/foodieplug-test/image/upload/"
            "v1/foodieplug/avatars/existing-avatar.png",
        )

    def test_avatar_upload_uses_cloudinary_avatar_folder(self):
        with (
            mock.patch.object(
                CloudinaryMediaStorage,
                "_cloudinary_config",
                return_value=SimpleNamespace(
                    cloud_name="foodieplug-test",
                    api_key="test-key",
                    api_secret="test-secret",
                ),
            ),
            mock.patch(
                "cloudinary.uploader.upload",
                return_value={
                    "public_id": "foodieplug/avatars/test-avatar",
                    "format": "png",
                },
            ) as upload,
        ):
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": "",
                    "last_name": "",
                    "email": self.user.email,
                    "display_name": "",
                    "action": "profile",
                    "avatar": upload_file(),
                },
            )

        self.assertRedirects(response, reverse("profile"))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(
            profile.avatar.name,
            "cloudinary/foodieplug/avatars/test-avatar.png",
        )
        self.assertEqual(
            upload.call_args.kwargs["folder"],
            "foodieplug/avatars",
        )
        self.assertFalse(upload.call_args.kwargs["overwrite"])

    def test_missing_configuration_is_shown_without_exposing_secrets(self):
        with mock.patch.object(
            CloudinaryMediaStorage,
            "_cloudinary_config",
            side_effect=CloudinaryStorageNotConfigured(
                "Set CLOUDINARY_URL before uploading."
            ),
        ):
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": "",
                    "last_name": "",
                    "email": self.user.email,
                    "display_name": "",
                    "avatar": upload_file(),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CLOUDINARY_URL")
        self.assertNotContains(response, "test-secret")

    def test_failed_cloudinary_upload_returns_safe_error(self):
        with (
            mock.patch.object(
                CloudinaryMediaStorage,
                "_cloudinary_config",
                return_value=SimpleNamespace(
                    cloud_name="foodieplug-test",
                    api_key="test-key",
                    api_secret="test-secret",
                ),
            ),
            mock.patch(
                "cloudinary.uploader.upload",
                side_effect=RuntimeError("provider-secret-detail"),
            ),
        ):
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": "",
                    "last_name": "",
                    "email": self.user.email,
                    "display_name": "",
                    "avatar": upload_file(),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "could not be uploaded")
        self.assertNotContains(response, "provider-secret-detail")

    def test_invalid_avatar_is_rejected_before_cloudinary_upload(self):
        with mock.patch("cloudinary.uploader.upload") as upload:
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": "",
                    "last_name": "",
                    "email": self.user.email,
                    "display_name": "",
                    "avatar": upload_file(
                        content=b"not an image",
                        content_type="image/png",
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "valid JPG, PNG or WebP")
        upload.assert_not_called()

    def test_avatar_over_five_mib_is_rejected_before_cloudinary_upload(self):
        with mock.patch("cloudinary.uploader.upload") as upload:
            response = self.client.post(
                reverse("profile"),
                {
                    "first_name": "",
                    "last_name": "",
                    "email": self.user.email,
                    "display_name": "",
                    "avatar": upload_file(
                        content=b"x" * (5 * 1024 * 1024 + 1),
                    ),
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "smaller than 5 MB")
        upload.assert_not_called()

    def test_empty_avatar_renders_without_cloudinary_configuration(self):
        response = self.client.get(reverse("profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Choose photo")
