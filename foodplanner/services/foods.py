from apps.foods.models import Food, FoodCategory
from django.db import transaction


from django.db import transaction
from apps.foods.models import Food, FoodCategory


# Create new food
@transaction.atomic
def create_food(
    name,
    category,
    default_unit,
    is_perishable,
    shelf_life,
    image=None,
):
    """Create a new food."""

    category_obj = FoodCategory.objects.get(pk=category)

    food = Food.objects.create(
        name=name,
        category=category_obj,
        default_unit=default_unit,
        is_perishable=is_perishable,
        shelf_life=shelf_life or None,
        image=image or None,
    )

    return food


# Get all active foods in the database
def get_all_foods():
    """Return all active foods."""
    return Food.objects.filter(is_active=True)


# Get one active food by ID
def get_food_by_id(food_id):
    """Return an active food by its ID."""
    return Food.objects.filter(
        id=food_id,
        is_active=True
    ).first()


# Get one active food by exact name
def get_food_by_name(name):
    """Return an active food by its exact name."""
    return Food.objects.filter(
        name__iexact=name.strip(),
        is_active=True
    ).first()


# Search active foods by name
def search_foods(query):
    """Return active foods matching the search query."""
    query = query.strip()

    if not query:
        return Food.objects.none()

    return Food.objects.filter(
        name__icontains=query,
        is_active=True
    )


# Get active foods by category
def get_foods_by_category(category_id):
    """Return active foods belonging to a category."""
    return Food.objects.filter(
        category_id=category_id,
        is_active=True
    )


# Get all food categories
def get_all_categories():
    """Return all food categories."""
    return FoodCategory.objects.all()



@transaction.atomic
def update_food(
    food_id,
    name,
    category,
    default_unit,
    is_perishable,
    shelf_life,
    image=None,
    clear_image=False,
):
    """Update an active food without deleting its existing image by default."""

    food = Food.objects.select_for_update().filter(
        pk=food_id,
        is_active=True,
    ).first()

    if food is None:
        return None

    food.name = name
    food.category = FoodCategory.objects.get(pk=category)
    food.default_unit = default_unit
    food.is_perishable = is_perishable
    food.shelf_life = shelf_life or None

    if clear_image:
        food.image = None
    elif image:
        food.image = image

    food.save()
    return food


@transaction.atomic
def archive_food(food_id):
    """Soft-delete a food while preserving its database record."""

    food = Food.objects.select_for_update().filter(
        pk=food_id,
        is_active=True,
    ).first()

    if food is None:
        return False

    food.is_active = False
    food.save(update_fields=["is_active", "updated_at"])
    return True
