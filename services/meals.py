from datetime import date as date_type
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Exists, OuterRef

from apps.meals.models import Meal, MealIngredient, MealSchedule, UserMealPreference


def _whole_number(value, label):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a whole number.")
    if not number.is_finite() or number != number.to_integral_value():
        raise ValueError(f"{label} must be a whole number.")
    return int(number)


def get_user_available_meals(user):
    """Active catalogue meals not archived by this user."""
    meals = Meal.objects.filter(is_active=True)

    if user is None or not getattr(user, "is_authenticated", False):
        return meals

    archived = UserMealPreference.objects.filter(
        user=user,
        meal_id=OuterRef("pk"),
        is_archived=True,
    )
    favorites = UserMealPreference.objects.filter(
        user=user,
        meal_id=OuterRef("pk"),
        is_favorite=True,
        is_archived=False,
    )
    return (
        meals.annotate(
            is_favorite=Exists(favorites),
        )
        .annotate(is_archived=Exists(archived))
        .filter(is_archived=False)
    )


def get_user_available_meal(user, meal_id):
    """Get an active meal that this user has not archived."""
    return get_user_available_meals(user).filter(
        pk=meal_id
    ).first()


def search_user_available_meals(user, query):
    """Search active, non-archived meals for this user."""
    query = (query or "").strip()

    if not query:
        return get_user_available_meals(user).none()

    return get_user_available_meals(user).filter(
        name__icontains=query
    )


def get_user_archived_meals(user):
    """Return meals archived for this user, without changing the global catalogue."""
    return Meal.objects.filter(
        is_active=True,
        user_preferences__user=user,
        user_preferences__is_archived=True,
    ).order_by("name")


def get_user_favorite_meals(user):
    """Return this user's favorites that are not archived."""
    return get_user_available_meals(user).filter(
        user_preferences__user=user,
        user_preferences__is_favorite=True,
    ).order_by("name")


def get_user_meal_preference(user, meal):
    """Get or create this user's preference for a meal."""
    preference, _ = UserMealPreference.objects.get_or_create(
        user=user,
        meal=meal,
    )
    return preference


def is_user_favorite(user, meal):
    """Check favorite state without creating a preference row."""
    return UserMealPreference.objects.filter(
        user=user,
        meal=meal,
        is_favorite=True,
    ).exists()



# Get all active meals
def get_all_meals():
    """Return all active meals."""

    return Meal.objects.filter(
        is_active=True
    )


# Get one active meal by ID
def get_meal_by_id(meal_id):
    """Return one active meal by ID."""

    return Meal.objects.filter(
        id=meal_id,
        is_active=True
    ).first()


# Search meals by name
def search_meals(query):
    """Return active meals matching the search query."""

    query = query.strip()

    if not query:
        return Meal.objects.none()

    return Meal.objects.filter(
        name__icontains=query,
        is_active=True
    )


# Get ingredients belonging to a meal
def get_meal_ingredients(meal_id):
    """Return all ingredients belonging to a meal."""

    return MealIngredient.objects.filter(
        meal_id=meal_id
    ).select_related("food")



# Create a meal
@transaction.atomic
def create_meal(
    name,
    description="",
    instructions="",
    prep_time=None,
    cook_time=None,
    image=None
):
    """Create a new meal, including an optional uploaded image."""

    name = (name or "").strip()
    if not name:
        raise ValueError("Meal name is required.")
    if len(name) > 150:
        raise ValueError("Meal name must be 150 characters or fewer.")
    for label, value in (("Prep time", prep_time), ("Cook time", cook_time)):
        if value is not None:
            value = _whole_number(value, f"{label} in minutes")
            if value < 0:
                raise ValueError(f"{label} cannot be negative.")
            if label == "Prep time":
                prep_time = value
            else:
                cook_time = value

    meal = Meal.objects.create(
        name=name,
        description=description,
        instructions=instructions,
        prep_time=prep_time,
        cook_time=cook_time,
        image=image
    )

    return meal



# Add ingredient to a meal
def add_meal_ingredient(
    meal,
    food,
    quantity,
    unit
):
    """Add an ingredient to a meal."""

    try:
        quantity = Decimal(quantity)
        rounded_quantity = quantity.quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Enter a valid ingredient quantity.")

    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Ingredient quantity must be greater than zero.")
    if quantity != rounded_quantity:
        raise ValueError("Ingredient quantities can have at most two decimal places.")
    if rounded_quantity >= Decimal("100000000"):
        raise ValueError("Ingredient quantity is too large.")
    if not isinstance(unit, str) or not unit.strip() or len(unit.strip()) > 20:
        raise ValueError("Enter a valid ingredient unit.")
    unit = unit.strip()

    ingredient, created = MealIngredient.objects.get_or_create(
        meal=meal,
        food=food,
        unit=unit,
        defaults={
            "quantity": quantity
        }
    )

    if not created:
        updated_quantity = ingredient.quantity + rounded_quantity
        if updated_quantity >= Decimal("100000000"):
            raise ValueError("Ingredient quantity is too large.")
        ingredient.quantity = updated_quantity

        ingredient.save(
            update_fields=["quantity"]
        )

    return ingredient


# Remove meal ingredient
def remove_meal_ingredient(
    meal,
    food,
    unit
):
    """Remove an ingredient from a meal."""

    ingredient = MealIngredient.objects.filter(
        meal=meal,
        food=food,
        unit=unit
    ).first()

    if ingredient is None:
        return False

    ingredient.delete()

    return True


# =========================================================
# MEAL SCHEDULE SERVICES
# =========================================================

# Get a user's meal schedule
def get_user_schedule(user):
    """Return all meal schedules belonging to a user."""

    return MealSchedule.objects.filter(
        user=user
    ).select_related("meal")


# Get schedule for a specific date
def get_schedule_for_date(user, date):
    """Return all meals scheduled for a specific date."""

    return MealSchedule.objects.filter(
        user=user,
        date=date
    ).select_related("meal")


# Get a specific scheduled meal
def get_scheduled_meal(user, schedule_id):
    """Return a specific scheduled meal belonging to a user."""

    return MealSchedule.objects.filter(
        id=schedule_id,
        user=user
    ).select_related("meal").first()


# Schedule a meal
def schedule_meal(
    user,
    meal,
    date,
    meal_type,
    servings=1
):
    """
    Schedule a meal for a user.

    If a meal already exists for the same
    date and meal type, update it.
    """

    if not isinstance(date, date_type):
        raise ValueError("Choose a valid date.")
    if meal_type not in MealSchedule.MealType.values:
        raise ValueError("Choose a valid meal type.")
    if not meal or not Meal.objects.filter(pk=meal.pk, is_active=True).exists():
        raise ValueError("Selected meal is not available.")
    servings = _whole_number(servings, "Servings")
    if servings <= 0:
        raise ValueError("Servings must be greater than zero.")
    if UserMealPreference.objects.filter(
        user=user,
        meal=meal,
        is_archived=True,
    ).exists():
        raise ValueError("That meal is archived and cannot be scheduled.")

    schedule, created = MealSchedule.objects.update_or_create(
        user=user,
        date=date,
        meal_type=meal_type,
        defaults={
            "meal": meal,
            "servings": servings
        }
    )

    return schedule


@transaction.atomic
def move_scheduled_meal(user, schedule_id, target_date, target_meal_type):
    """Move a user's scheduled meal without replacing an occupied slot."""
    schedule = get_scheduled_meal(user, schedule_id)
    if schedule is None:
        return None
    if not isinstance(target_date, date_type):
        raise ValueError("Choose a valid date.")
    if target_meal_type not in MealSchedule.MealType.values:
        raise ValueError("Choose a valid meal type.")
    if schedule.date == target_date and schedule.meal_type == target_meal_type:
        return schedule
    if MealSchedule.objects.filter(
        user=user,
        date=target_date,
        meal_type=target_meal_type,
    ).exists():
        raise ValueError("That meal-planner slot is already occupied.")

    schedule.date = target_date
    schedule.meal_type = target_meal_type
    schedule.save(update_fields=["date", "meal_type", "updated_at"])
    return schedule


# Update servings
def update_servings(
    user,
    schedule_id,
    servings
):
    """Update the number of servings for a scheduled meal."""

    schedule = get_scheduled_meal(
        user=user,
        schedule_id=schedule_id
    )

    if schedule is None:
        return None

    servings = _whole_number(servings, "Servings")
    if servings <= 0:
        raise ValueError(
            "Servings must be greater than zero."
        )

    schedule.servings = servings

    schedule.save(
        update_fields=["servings", "updated_at"]
    )

    return schedule


# Remove a scheduled meal
def remove_scheduled_meal(
    user,
    schedule_id
):
    """Remove a meal from the user's timetable."""

    schedule = get_scheduled_meal(
        user=user,
        schedule_id=schedule_id
    )

    if schedule is None:
        return False

    schedule.delete()

    return True