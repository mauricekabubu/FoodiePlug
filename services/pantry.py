from datetime import date, timedelta
from decimal import Decimal

from django.db import models

from apps.pantry.models import PantryItem


# =========================================================
# PANTRY RETRIEVAL
# =========================================================

def get_user_pantry(user):
    """
    Return all pantry items belonging to the user.
    """

    return PantryItem.objects.filter(
        user=user
    ).select_related(
        "food"
    )


def get_pantry_item(user, pantry_item_id):
    """
    Return a specific pantry item belonging to the user.
    """

    return PantryItem.objects.filter(
        id=pantry_item_id,
        user=user
    ).select_related(
        "food"
    ).first()


# =========================================================
# PANTRY MANAGEMENT
# =========================================================

def add_to_pantry(
    user,
    food,
    quantity,
    unit,
    minimum_quantity=0,
    storage="pantry",
    acquired_at=None,
    expires_at=None,
    notes=""
):
    """
    Add food to a user's pantry.

    If the same food and unit already exist,
    increase the existing quantity.
    """

    if quantity <= 0:
        raise ValueError(
            "Quantity must be greater than zero."
        )

    if minimum_quantity < 0:
        raise ValueError(
            "Minimum quantity cannot be negative."
        )

    pantry_item, created = PantryItem.objects.get_or_create(
        user=user,
        food=food,
        unit=unit,
        defaults={
            "quantity": quantity,
            "minimum_quantity": minimum_quantity,
            "storage": storage,
            "acquired_at": acquired_at,
            "expires_at": expires_at,
            "notes": notes,
        }
    )

    if not created:
        pantry_item.quantity += quantity

        # Update metadata when adding to an
        # existing pantry item.
        pantry_item.minimum_quantity = minimum_quantity
        pantry_item.storage = storage
        pantry_item.acquired_at = acquired_at
        pantry_item.expires_at = expires_at
        pantry_item.notes = notes

        pantry_item.save(
            update_fields=[
                "quantity",
                "minimum_quantity",
                "storage",
                "acquired_at",
                "expires_at",
                "notes",
                "updated_at",
            ]
        )

    return pantry_item


def update_pantry_item(
    user,
    pantry_item_id,
    quantity=None,
    unit=None,
    minimum_quantity=None,
    storage=None,
    acquired_at=None,
    expires_at=None,
    notes=None
):
    """
    Update the details of an existing pantry item.

    Only values explicitly provided are updated.
    """

    pantry_item = get_pantry_item(
        user=user,
        pantry_item_id=pantry_item_id
    )

    if pantry_item is None:
        return None

    if quantity is not None:
        if quantity <= 0:
            pantry_item.delete()
            return None

        pantry_item.quantity = quantity

    if unit is not None:
        pantry_item.unit = unit

    if minimum_quantity is not None:
        if minimum_quantity < 0:
            raise ValueError(
                "Minimum quantity cannot be negative."
            )

        pantry_item.minimum_quantity = minimum_quantity

    if storage is not None:
        pantry_item.storage = storage

    if acquired_at is not None:
        pantry_item.acquired_at = acquired_at

    if expires_at is not None:
        pantry_item.expires_at = expires_at

    if notes is not None:
        pantry_item.notes = notes

    pantry_item.save()

    return pantry_item


def update_quantity(user, pantry_item_id, quantity):
    """
    Set the pantry item's quantity to a new value.

    If quantity is zero or less, remove the item.
    """

    pantry_item = get_pantry_item(
        user=user,
        pantry_item_id=pantry_item_id
    )

    if pantry_item is None:
        return None

    if quantity <= 0:
        pantry_item.delete()
        return None

    pantry_item.quantity = quantity

    pantry_item.save(
        update_fields=[
            "quantity",
            "updated_at",
        ]
    )

    return pantry_item


def remove_from_pantry(user, pantry_item_id):
    """
    Remove a pantry item completely.
    """

    pantry_item = get_pantry_item(
        user=user,
        pantry_item_id=pantry_item_id
    )

    if pantry_item is None:
        return False

    pantry_item.delete()

    return True


# =========================================================
# CONSUMPTION
# =========================================================

def consume_from_pantry(user, pantry_item_id, quantity):
    """
    Consume part of a pantry item.

    If the remaining quantity reaches zero,
    the pantry item is removed.
    """

    pantry_item = get_pantry_item(
        user=user,
        pantry_item_id=pantry_item_id
    )

    if pantry_item is None:
        return None

    if quantity <= 0:
        raise ValueError(
            "Quantity consumed must be greater than zero."
        )

    if quantity > pantry_item.quantity:
        raise ValueError(
            "You cannot consume more than the available quantity."
        )

    pantry_item.quantity -= quantity

    if pantry_item.quantity <= 0:
        pantry_item.delete()
        return None

    pantry_item.save(
        update_fields=[
            "quantity",
            "updated_at",
        ]
    )

    return pantry_item


# =========================================================
# STATUS
# =========================================================

def get_pantry_item_status(pantry_item):
    """
    Determine the current pantry status.

    Returns:
        available
        low
        out
    """

    if pantry_item.quantity <= 0:
        return "out"

    if (
        pantry_item.minimum_quantity > 0
        and pantry_item.quantity <= pantry_item.minimum_quantity
    ):
        return "low"

    return "available"


def get_running_low_items(user):
    """
    Return pantry items whose quantity is at or below
    their minimum quantity.
    """

    return PantryItem.objects.filter(
        user=user,
        minimum_quantity__gt=0,
        quantity__lte=models.F("minimum_quantity")
    ).select_related(
        "food"
    )


# =========================================================
# EXPIRY
# =========================================================

def get_expiring_items(user, days=3):
    """
    Return pantry items expiring within the given
    number of days.
    """

    today = date.today()

    expiry_limit = today + timedelta(
        days=days
    )

    return PantryItem.objects.filter(
        user=user,
        expires_at__isnull=False,
        expires_at__gte=today,
        expires_at__lte=expiry_limit,
    ).select_related(
        "food"
    ).order_by(
        "expires_at"
    )


def get_expired_items(user):
    """
    Return pantry items that have already expired.
    """

    return PantryItem.objects.filter(
        user=user,
        expires_at__isnull=False,
        expires_at__lt=date.today(),
    ).select_related(
        "food"
    ).order_by(
        "expires_at"
    )