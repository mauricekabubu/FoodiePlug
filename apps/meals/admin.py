from django.contrib import admin
from .models import Meal, MealIngredient, MealSchedule

# Register your models here.
admin.site.register(Meal)
admin.site.register(MealIngredient)
admin.site.register(MealSchedule)

