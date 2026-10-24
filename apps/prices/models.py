from django.conf import settings
from django.db import models

from apps.foods.models import Food


class PriceEntry(models.Model):

    class UnitChoices(models.TextChoices):
        KG = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITRE = "l", "Litre"
        ML = "ml", "Millilitre"
        PIECE = "piece", "Piece"
        BUNCH = "bunch", "Bunch"
        PACKET = "packet", "Packet"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="price_entries"
    )

    food = models.ForeignKey(
        Food,
        on_delete=models.PROTECT,
        related_name="price_entries"
    )

    price = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    unit = models.CharField(
        max_length=20,
        choices=UnitChoices.choices
    )

    recorded_at = models.DateTimeField()

    source = models.CharField(
        max_length=100,
        blank=True
    )

    class Meta:
        ordering = ["-recorded_at", "-pk"]
        indexes = [
            models.Index(
                fields=["user", "-recorded_at", "-id"],
                name="price_user_recent_idx",
            ),
            models.Index(
                fields=["user", "food", "-recorded_at"],
                name="price_user_food_recent_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.food.name} - "
            f"KES {self.price}/{self.quantity} {self.unit}"
        )