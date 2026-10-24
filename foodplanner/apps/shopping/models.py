from django.db import models
from django.conf import settings

from apps.foods.models import Food


class ShoppingList(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="shopping_lists"
    )

    name = models.CharField(
        max_length=150,
        default="Shopping List"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "-updated_at", "-id"],
                name="shoplist_user_updated_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.name}"


class ShoppingItem(models.Model):

    class UnitChoices(models.TextChoices):
        KG = "kg", "Kilograms"
        G = "g", "Grams"
        L = "l", "Litres"
        ML = "ml", "Millilitres"
        PIECE = "piece", "Piece"
        PACK = "pack", "Pack"
        BUNCH = "bunch", "Bunch"
        ROSE = "rose", "Rose"

    shopping_list = models.ForeignKey(
        ShoppingList,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="items"
    )

    food = models.ForeignKey(
        Food,
        on_delete=models.PROTECT,
        related_name="shopping_items"
    )

    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    unit = models.CharField(
        max_length=20,
        choices=UnitChoices.choices
    )

    is_purchased = models.BooleanField(
        default=False
    )

    purchased_at = models.DateTimeField(
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )
    
    is_archived = models.BooleanField(
        default=False,
        db_index=True,
    )

    class Meta:
        ordering = ["is_purchased", "food__name", "pk"]
        indexes = [
            models.Index(
                fields=["shopping_list", "is_purchased"],
                name="shopitem_list_status_idx",
            ),
        ]

    def __str__(self):
        return f"{self.food.name} - {self.quantity} {self.unit}"