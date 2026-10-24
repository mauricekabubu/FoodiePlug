from django.db import models
from django.conf import settings

from apps.foods.models import Food


class PantryItem(models.Model):

    # =========================================================
    # CHOICES
    # =========================================================

    class UnitChoices(models.TextChoices):
        KG = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITRE = "l", "Litre"
        ML = "ml", "Millilitre"
        PIECE = "piece", "Piece"
        BUNCH = "bunch", "Bunch"
        PACKET = "packet", "Packet"

    class StorageChoices(models.TextChoices):
        PANTRY = "pantry", "Pantry"
        REFRIGERATOR = "refrigerator", "Refrigerator"
        FREEZER = "freezer", "Freezer"
        OTHER = "other", "Other"

    # =========================================================
    # OWNERSHIP
    # =========================================================

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="pantry_items"
    )

    # =========================================================
    # FOOD
    # =========================================================

    food = models.ForeignKey(
        Food,
        on_delete=models.PROTECT,
        related_name="pantry_items"
    )

    # =========================================================
    # QUANTITY
    # =========================================================

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    minimum_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    unit = models.CharField(
        max_length=20,
        choices=UnitChoices.choices,
        default=UnitChoices.PIECE
    )

    # =========================================================
    # STORAGE
    # =========================================================

    storage = models.CharField(
        max_length=20,
        choices=StorageChoices.choices,
        default=StorageChoices.PANTRY
    )

    # =========================================================
    # DATES
    # =========================================================

    acquired_at = models.DateField(
        null=True,
        blank=True
    )

    expires_at = models.DateField(
        null=True,
        blank=True
    )

    # =========================================================
    # NOTES
    # =========================================================

    notes = models.TextField(
        blank=True
    )

    # =========================================================
    # TIMESTAMPS
    # =========================================================

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    # =========================================================
    # META
    # =========================================================

    class Meta:
        ordering = [
            "expires_at",
            "food__name",
            "pk",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "user",
                    "food",
                    "unit"
                ],
                name="unique_user_food_unit"
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "expires_at"],
                name="pantry_user_expiry_idx",
            ),
        ]

    # =========================================================
    # STRING REPRESENTATION
    # =========================================================

    def __str__(self):
        return (
            f"{self.food.name} - "
            f"{self.quantity} {self.unit}"
        )
