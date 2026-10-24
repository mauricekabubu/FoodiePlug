from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db.models import Q

from apps.foods.models import Food

# Create your models here.
class Meal(models.Model):
    name = models.CharField(max_length=150, unique=True)
    description = models.TextField(null=True, blank=True)
    instructions = models.TextField(null=True, blank=True)
    
    prep_time = models.PositiveIntegerField(
        null=True, blank=True, help_text="Preparation time in minutes"
    )
    cook_time = models.PositiveIntegerField(
        null=True, blank=True, help_text="Cooking time in minutes"
    )
    
    image = models.ImageField(
        upload_to="foods/",
        blank=True,
        null=True
    )
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name", "pk"]
        indexes = [
            models.Index(
                fields=["is_active", "name"],
                name="meal_active_name_idx",
            ),
        ]
        
    def __str__(self):
        return self.name
    
class MealIngredient(models.Model):
    meal = models.ForeignKey(
        Meal,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="ingredients",
    )
    food = models.ForeignKey(Food, on_delete=models.PROTECT, related_name="meal_ingredients")
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0.01)],
        help_text="Per-serving quantity; cooking multiplies it by the scheduled servings.",
    )
    unit = models.CharField(max_length=20)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["meal", "food", "unit"],
                name="unique_meal_food_unit"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="meal_ingredient_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.meal.name} - {self.food.name}"    


class MealSchedule(models.Model):
    class MealType(models.TextChoices):
        BREAKFAST = "breakfast", "Breakfast"
        LUNCH = "lunch", "Lunch"
        SUPPER = "supper", "Supper"
        SNACK = "snack", "Snack"
        
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="meal_schedules",
    )
    meal = models.ForeignKey(Meal, on_delete=models.PROTECT, related_name="schedules")
    date = models.DateField()
    meal_type = models.CharField(
        max_length=20, choices=MealType.choices
    )
    
    servings = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    is_cooked = models.BooleanField(default=False)
    cooked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["date", "meal_type"]

        constraints = [
            models.UniqueConstraint(
                fields=["user", "date", "meal_type"],
                name="unique_user_date_meal_type"
            ),
            models.CheckConstraint(
                condition=Q(servings__gt=0),
                name="meal_schedule_servings_positive",
            ),
            models.CheckConstraint(
                condition=Q(meal_type__in=("breakfast", "lunch", "supper", "snack")),
                name="meal_schedule_type_valid",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.date} - {self.meal_type}"
    

class MealConsumption(models.Model):
    schedule = models.OneToOneField(
        MealSchedule,
        on_delete=models.PROTECT,
        related_name="consumption",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="meal_consumptions",
    )
    cooked_at = models.DateTimeField()

    def __str__(self):
        return f"{self.schedule} cooked by {self.user}"


class MealConsumptionItem(models.Model):
    consumption = models.ForeignKey(
        MealConsumption,
        on_delete=models.PROTECT,
        related_name="items",
    )
    pantry_item = models.ForeignKey(
        "pantry.PantryItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meal_consumptions",
    )
    food = models.ForeignKey(Food, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=20)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="meal_consumption_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.food.name} - {self.quantity} {self.unit}"


class UserMealPreference(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_index=False,
        related_name="meal_preferences",
    )
    meal = models.ForeignKey(
        Meal,
        on_delete=models.CASCADE,
        related_name="user_preferences",
    )
    is_archived = models.BooleanField(default=False)
    is_favorite = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "meal"],
                name="unique_user_meal_preference",
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "is_archived", "is_favorite"],
                name="mealpref_user_flags_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user} — {self.meal.name}"
