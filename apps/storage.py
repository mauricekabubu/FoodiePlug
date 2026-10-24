"""Cloudinary-backed default storage with support for existing local media."""

import logging
import os
import uuid
from urllib.request import urlopen

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

logger = logging.getLogger(__name__)

CLOUDINARY_PREFIX = "cloudinary/"
ALLOWED_IMAGE_FORMATS = {"jpg", "jpeg", "png", "webp"}


class CloudinaryStorageError(Exception):
    """A safe-to-display error raised by Cloudinary media operations."""


class CloudinaryStorageNotConfigured(CloudinaryStorageError):
    """The environment does not contain complete Cloudinary credentials."""


class CloudinaryMediaStorage(FileSystemStorage):
    """Save new images to Cloudinary and keep existing local paths readable."""

    def _is_cloudinary_name(self, name):
        return str(name).replace("\\", "/").startswith(CLOUDINARY_PREFIX)

    def _cloudinary_config(self):
        import cloudinary

        try:
            config = cloudinary.config()
        except ValueError:
            raise CloudinaryStorageNotConfigured(
                "Cloudinary credentials are invalid. Check CLOUDINARY_URL."
            ) from None
        if not all((
            config.cloud_name,
            config.api_key,
            config.api_secret,
        )):
            raise CloudinaryStorageNotConfigured(
                "Image uploads require Cloudinary credentials. Configure "
                "CLOUDINARY_URL and try again."
            )
        return config

    def _save(self, name, content):
        config = self._cloudinary_config()
        normalized_name = str(name).replace("\\", "/")
        original_extension = os.path.splitext(normalized_name)[1].lower().lstrip(".")

        if original_extension not in ALLOWED_IMAGE_FORMATS:
            raise CloudinaryStorageError(
                "Only JPG, PNG, and WebP images can be uploaded."
            )

        source_folder = normalized_name.split("/", 1)[0].lower()
        cloudinary_folder = (
            "foodieplug/avatars"
            if source_folder == "profiles"
            else "foodieplug/foods"
        )
        public_id = uuid.uuid4().hex

        try:
            import cloudinary.uploader

            result = cloudinary.uploader.upload(
                content,
                folder=cloudinary_folder,
                public_id=public_id,
                overwrite=False,
                unique_filename=False,
                resource_type="image",
                allowed_formats=sorted(ALLOWED_IMAGE_FORMATS),
            )
        except Exception as error:
            logger.warning(
                "Cloudinary image upload failed (%s).",
                type(error).__name__,
            )
            raise CloudinaryStorageError(
                "The image could not be uploaded. Check the Cloudinary "
                "configuration and try again."
            ) from None

        uploaded_format = str(result.get("format", "")).lower()
        uploaded_public_id = result.get("public_id")
        if (
            not uploaded_public_id
            or uploaded_format not in ALLOWED_IMAGE_FORMATS
        ):
            logger.error("Cloudinary returned an invalid image result.")
            raise CloudinaryStorageError(
                "The image upload did not complete. Please try again."
            )

        return f"{CLOUDINARY_PREFIX}{uploaded_public_id}.{uploaded_format}"

    def url(self, name):
        if not self._is_cloudinary_name(name):
            return super().url(name)

        config = self._cloudinary_config()
        stored_name = str(name).replace("\\", "/")[len(CLOUDINARY_PREFIX):]
        public_id, extension = os.path.splitext(stored_name)
        extension = extension.lower().lstrip(".")
        if extension not in ALLOWED_IMAGE_FORMATS:
            raise CloudinaryStorageError(
                "The stored image reference is invalid."
            )

        import cloudinary

        url, _ = cloudinary.utils.cloudinary_url(
            public_id,
            format=extension,
            secure=True,
            cloud_name=config.cloud_name,
        )
        return url

    def path(self, name):
        if self._is_cloudinary_name(name):
            raise NotImplementedError(
                "Cloudinary images do not have a local filesystem path."
            )
        return super().path(name)

    def _open(self, name, mode="rb"):
        if not self._is_cloudinary_name(name):
            return super()._open(name, mode)

        try:
            with urlopen(self.url(name), timeout=20) as response:
                return ContentFile(response.read(), name=os.path.basename(name))
        except Exception as error:
            logger.warning(
                "Cloudinary image download failed (%s).",
                type(error).__name__,
            )
            raise CloudinaryStorageError(
                "The image could not be loaded from Cloudinary."
            ) from None

    def size(self, name):
        if not self._is_cloudinary_name(name):
            return super().size(name)

        config = self._cloudinary_config()
        stored_name = str(name).replace("\\", "/")[len(CLOUDINARY_PREFIX):]
        public_id = os.path.splitext(stored_name)[0]

        try:
            import cloudinary.api

            result = cloudinary.api.resource(
                public_id,
                resource_type="image",
                cloud_name=config.cloud_name,
            )
            return int(result["bytes"])
        except Exception as error:
            logger.warning(
                "Cloudinary image metadata lookup failed (%s).",
                type(error).__name__,
            )
            raise CloudinaryStorageError(
                "The image size could not be read from Cloudinary."
            ) from None

    def delete(self, name):
        if not self._is_cloudinary_name(name):
            return super().delete(name)

        config = self._cloudinary_config()
        stored_name = str(name).replace("\\", "/")[len(CLOUDINARY_PREFIX):]
        public_id = os.path.splitext(stored_name)[0]

        try:
            import cloudinary.uploader

            cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
                invalidate=False,
                cloud_name=config.cloud_name,
            )
        except Exception as error:
            logger.warning(
                "Cloudinary image deletion failed (%s).",
                type(error).__name__,
            )
            raise CloudinaryStorageError(
                "The image could not be removed from Cloudinary."
            ) from None
