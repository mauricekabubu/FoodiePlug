from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile


@receiver(post_save, sender=get_user_model())
def create_user_profile(sender, instance, created, **kwargs):
    if created and not kwargs.get("raw", False):
        Profile.objects.get_or_create(
            user=instance,
            defaults={"display_name": instance.get_full_name().strip()},
        )
