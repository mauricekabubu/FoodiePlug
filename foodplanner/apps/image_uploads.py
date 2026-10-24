"""Shared server-side validation for supported user-uploaded images."""

from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_TYPES = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/webp": "WEBP",
}
MAX_IMAGE_BYTES = 5*1024*1024


def validate_image_upload(uploaded_file, max_bytes=MAX_IMAGE_BYTES):
    """Validate declared type, size, and actual decoded image format."""
    if uploaded_file.content_type not in ALLOWED_IMAGE_TYPES:
        return "Choose a JPG, PNG or WebP image."

    if uploaded_file.size > max_bytes:
        return "The image must be smaller than 5 MB."

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as image:
            image_format = image.format
            image.verify()
    except (
        Image.DecompressionBombError,
        OSError,
        UnidentifiedImageError,
        ValueError,
    ):
        return "Choose a valid JPG, PNG or WebP image."
    finally:
        uploaded_file.seek(0)

    if image_format != ALLOWED_IMAGE_TYPES[uploaded_file.content_type]:
        return "Choose a valid JPG, PNG or WebP image."

    return None
