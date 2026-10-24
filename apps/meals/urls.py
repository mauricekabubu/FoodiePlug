from django.urls import path
from django.views.generic import RedirectView

from . import views


app_name = "meals"


urlpatterns = [
    # ---------- Meal library ----------
    path("", views.meal_library, name="meal_library"),
    path(
        "meals/",
        RedirectView.as_view(pattern_name="meals:meal_library", query_string=True),
    ),
    path("meal_detail/<int:meal_id>/", views.meal_detail, name="meal_detail"),
    path("meal_search/", views.meal_search, name="meal_search"),
    path("create_meal/", views.create_meal_view, name="create_meal"),
    path("edit/<int:meal_id>/", views.edit_meal, name="edit_meal"),
    path("add_ingredient/<int:meal_id>/", views.add_ingredient, name="add_ingredient"),
    # The view takes (request, meal_id) and reads food_id/unit from the POST body,
    # so the URL must not capture an ingredient_id.
    path("remove_ingredient/<int:meal_id>/", views.remove_ingredient, name="remove_ingredient"),

    # ---------- Archive (soft delete) ----------
    path("archive/", views.archived_meals, name="archived_meals"),
    path("archive_meal/<int:meal_id>/", views.archive_meal, name="archive_meal"),
    path("restore_meal/<int:meal_id>/", views.restore_meal, name="restore_meal"),

    # ---------- Timetable ----------
    path("timetable/", views.timetable, name="timetable"),
    path("daily_timetable/", views.daily_timetable, name="daily_timetable"),
    path("generate_timetable/", views.generate_timetable, name="generate_timetable"),
    path("schedule_meal/", views.schedule_meal_view, name="schedule_meal"),
    path("update_meal_servings/<int:schedule_id>/", views.update_meal_servings, name="update_meal_servings"),
    path("remove_meal_schedule/<int:schedule_id>/", views.remove_meal_schedule, name="remove_meal_schedule"),
    path("cook_meal_schedule/<int:schedule_id>/", views.cook_meal_schedule, name="cook_meal_schedule"),

    # ---------- New for the weekly planner ----------
    path("move_meal_schedule/<int:schedule_id>/", views.move_meal_schedule, name="move_meal_schedule"),
    path("add_missing_to_shopping/<int:schedule_id>/", views.add_missing_to_shopping, name="add_missing_to_shopping"),
      # ---------- Favorites ----------
    path("favorites/", views.favorite_meals, name="favorite_meals"),
    path("toggle_favorite/<int:meal_id>/", views.toggle_favorite, name="toggle_favorite"),

]