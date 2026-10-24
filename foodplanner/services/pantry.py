from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_FLOOR

from django.db import models

from apps.pantry.models import PantryItem


UNIT_ALIASES = {
    "gram": "g",
    "grams": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
}

UNIT_FACTORS = {
    "kg": ("mass", Decimal("1000")),
    "g": ("mass", Decimal("1")),
    "l": ("volume", Decimal("1000")),
    "ml": ("volume", Decimal("1")),
}


def normalize_unit(unit):
    """Normalize only common, unambiguous spelling aliases."""
    normalized = (unit or "").strip().lower()
    return UNIT_ALIASES.get(normalized, normalized)


def unit_measure(unit):
    """Return a compatible dimension and factor into its base unit."""
    normalized = normalize_unit(unit)
    return UNIT_FACTORS.get(normalized, (f"unit:{normalized}", Decimal("1")))


def convert_quantity(quantity, from_unit, to_unit):
    """Convert mass or volume, or identical units; reject unlike dimensions."""
    source = normalize_unit(from_unit)
    target = normalize_unit(to_unit)
    source_dimension, source_factor = unit_measure(source)
    target_dimension, target_factor = unit_measure(target)
    if source_dimension != target_dimension:
        raise ValueError(f"Cannot convert {from_unit} to {to_unit}.")
    return Decimal(quantity) * source_factor / target_factor


def quantity_precision(quantity, decimal_places=2):
    """Whether a Decimal can be stored without rounding at the given precision."""
    value = Decimal(quantity)
    quantum = Decimal(1).scaleb(-decimal_places)
    try:
        return value.quantize(quantum) == value
    except InvalidOperation:
        return False


def allocate_consumption(required_base, pantry_rows, base_unit):
    """
    Allocate exact consumption across rows, preferring coarser units first.

    PantryItem quantities have two decimal places. Allocation is performed in
    base units, so no quantity is rounded or deducted beyond the requirement.
    """
    remaining = Decimal(required_base)
    allocations = []
    candidates = []

    for item in pantry_rows:
        dimension, factor = unit_measure(item.unit)
        expected_dimension, _ = unit_measure(base_unit)
        if dimension != expected_dimension or item.quantity <= 0:
            continue
        candidates.append((factor, item))

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    for factor, item in candidates:
        step = factor * Decimal("0.01")
        available_base = item.quantity * factor
        representable = (remaining / step).to_integral_value(rounding=ROUND_FLOOR) * step
        consumed_base = min(available_base, representable)
        if consumed_base <= 0:
            continue

        consumed_quantity = consumed_base / factor
        if not quantity_precision(consumed_quantity, 2):
            continue
        new_quantity = item.quantity - consumed_quantity
        if new_quantity < 0 or not quantity_precision(new_quantity, 2):
            continue

        allocations.append((item, consumed_quantity, new_quantity))
        remaining -= consumed_base

    return allocations, remaining


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
        "food",
        "food__category",
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