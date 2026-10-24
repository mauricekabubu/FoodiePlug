from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from decimal import Decimal

from apps.foods.models import Food
from apps.shopping.models import ShoppingList, ShoppingItem


# =========================================================
# SHOPPING LIST SERVICES
# =========================================================


@transaction.atomic
def create_shopping_list(user, name="Shopping List"):
    """
    Create a new shopping list for a user.
    """

    if not name or not name.strip():
        raise ValueError("Shopping list name cannot be empty.")

    return ShoppingList.objects.create(
        user=user,
        name=name.strip()
    )
    
    
def get_user_shopping_lists(user):
    """
    Return all shopping lists belonging to a user.
    """

    return (
        ShoppingList.objects
        .filter(user=user)
        .prefetch_related("items__food")
    )
    
def get_shopping_list(user, shopping_list_id):
    """
    Retrieve a specific shopping list belonging to a user.
    """

    try:
        return (
            ShoppingList.objects
            .get(
                id=shopping_list_id,
                user=user
            )
        )
    except ShoppingList.DoesNotExist:
        raise ValueError("Shopping list not found.")
    

def rename_shopping_list(user, shopping_list_id, name):
    """
    Rename a user's shopping list.
    """

    if not name or not name.strip():
        raise ValueError("Shopping list name cannot be empty.")

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    shopping_list.name = name.strip()
    shopping_list.save(update_fields=["name", "updated_at"])

    return shopping_list


def delete_shopping_list(user, shopping_list_id):
    """
    Delete a user's shopping list.
    """

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    shopping_list.delete()


# =========================================================
# SHOPPING ITEM SERVICES
# ===========================

@transaction.atomic
def add_shopping_item(
    user,
    shopping_list_id,
    food_id,
    quantity,
    unit
):
    """
    Add a food item to a shopping list.
    """

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    try:
        food = Food.objects.get(id=food_id)
    except Food.DoesNotExist:
        raise ValueError("Food not found.")
    
    quantity = Decimal(quantity)

    if quantity <= 0:
        raise ValueError(
            "Quantity must be greater than zero."
        )

    if not unit or not unit.strip():
        raise ValueError("Unit is required.")

    item = ShoppingItem.objects.create(
        shopping_list=shopping_list,
        food=food,
        quantity=Decimal(quantity),
        unit=unit
    )

    return item

def get_shopping_items(user, shopping_list_id):
    """
    Get all items belonging to a user's shopping list.
    """

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    return (
        shopping_list.items
        .select_related("food")
        .all()
    )


@transaction.atomic
def update_shopping_item(
    user,
    item_id,
    quantity=None,
    unit=None
):
    """
    Update quantity and/or unit of a shopping item.
    """

    try:
        item = ShoppingItem.objects.select_related(
            "shopping_list",
            "food"
        ).get(
            id=item_id,
            shopping_list__user=user
        )
    except ShoppingItem.DoesNotExist:
        raise ValueError("Shopping item not found.")
    
    quantity = Decimal(quantity)
    
    if quantity is not None:
        if quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero."
            )

        item.quantity = Decimal(quantity)

    if unit is not None:
        if not unit.strip():
            raise ValueError("Unit cannot be empty.")

        item.unit = unit

    item.save()

    return item


@transaction.atomic
def remove_shopping_item(user, item_id):
    """
    Remove an item from a user's shopping list.
    """

    try:
        item = ShoppingItem.objects.get(
            id=item_id,
            shopping_list__user=user
        )
    except ShoppingItem.DoesNotExist:
        raise ValueError("Shopping item not found.")

    item.delete()


# =========================================================
# PURCHASE SERVICES
# =========================================================


@transaction.atomic
def mark_item_purchased(user, item_id):
    """
    Mark a shopping item as purchased.
    """

    try:
        item = ShoppingItem.objects.get(
            id=item_id,
            shopping_list__user=user
        )
    except ShoppingItem.DoesNotExist:
        raise ValueError("Shopping item not found.")

    if item.is_purchased:
        return item

    item.is_purchased = True
    item.purchased_at = timezone.now()

    item.save(
        update_fields=[
            "is_purchased",
            "purchased_at",
            "updated_at"
        ]
    )

    return item


@transaction.atomic
def mark_item_unpurchased(user, item_id):
    """
    Mark a shopping item as not purchased.
    """

    try:
        item = ShoppingItem.objects.get(
            id=item_id,
            shopping_list__user=user
        )
    except ShoppingItem.DoesNotExist:
        raise ValueError("Shopping item not found.")

    item.is_purchased = False
    item.purchased_at = None

    item.save(
        update_fields=[
            "is_purchased",
            "purchased_at",
            "updated_at"
        ]
    )

    return item


# =========================================================
# SHOPPING LIST GENERATION
# =========================================================


@transaction.atomic
def add_foods_to_shopping_list(
    user,
    shopping_list_id,
    foods
):
    """
    Add multiple foods to a shopping list.

    Expected format:

    foods = [
        {
            "food_id": 1,
            "quantity": 2,
            "unit": "kg"
        },
        {
            "food_id": 2,
            "quantity": 4,
            "unit": "piece"
        }
    ]
    """

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    items = []

    for data in foods:

        food_id = data.get("food_id")
        quantity = data.get("quantity")
        unit = data.get("unit")

        if not food_id:
            raise ValueError(
                "Each item must have a food_id."
            )

        if quantity is None or quantity <= 0:
            raise ValueError(
                "Quantity must be greater than zero."
            )

        if not unit:
            raise ValueError(
                "Each item must have a unit."
            )

        try:
            food = Food.objects.get(id=food_id)
        except Food.DoesNotExist:
            raise ValueError(
                f"Food with id {food_id} not found."
            )

        items.append(
            ShoppingItem(
                shopping_list=shopping_list,
                food=food,
                quantity=quantity,
                unit=unit
            )
        )

    ShoppingItem.objects.bulk_create(items)

    return shopping_list.items.select_related("food").all()


# =========================================================
# SHOPPING LIST STATUS
# =========================================================


def get_shopping_list_progress(user, shopping_list_id):
    """
    Return shopping list completion information.
    """

    shopping_list = get_shopping_list(
        user,
        shopping_list_id
    )

    return get_shopping_list_progress_for_list(shopping_list)


def get_shopping_list_progress_for_list(shopping_list):
    """Aggregate progress from an already-authorized shopping list."""
    progress = shopping_list.items.aggregate(
        total=Count("id"),
        purchased=Count("id", filter=Q(is_purchased=True)),
    )
    total_items = progress["total"]
    purchased_items = progress["purchased"]

    remaining_items = total_items - purchased_items

    percentage = (
        (purchased_items / total_items) * 100
        if total_items > 0
        else 0
    )

    return {
        "total_items": total_items,
        "purchased_items": purchased_items,
        "remaining_items": remaining_items,
        "completion_percentage": round(
            percentage,
            2
        )
    }