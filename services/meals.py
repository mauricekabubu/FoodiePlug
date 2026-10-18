from django.db import transaction

from apps.meals.models import Meal, MealIngredient, MealSchedule


# =========================================================
# MEAL SERVICES
# =========================================================



from apps.meals.models import (
    Meal,
    MealIngredient,
    MealSchedule,
    UserMealPreference,
)


def get_user_available_meals(user):
    """Active catalogue meals not archived by this user."""
    meals = Meal.objects.filter(is_active=True)

    if user is None or not getattr(user, "is_authenticated", False):
        return meals

    return meals.exclude(
        user_preferences__user=user,
        user_preferences__is_archived=True,
    ).distinct()


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

    ingredient, created = MealIngredient.objects.get_or_create(
        meal=meal,
        food=food,
        unit=unit,
        defaults={
            "quantity": quantity
        }
    )

    if not created:
        ingredient.quantity += quantity

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