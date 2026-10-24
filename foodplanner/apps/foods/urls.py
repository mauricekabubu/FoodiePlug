
from django.urls import path
from . import views

app_name = "foods"

urlpatterns = [
    path("", views.food_library, name="foods"),
    path("detail/<int:food_id>/", views.food_detail, name="detail"),
    path("search/", views.food_search, name="search"),
    path("category/<int:category_id>/", views.food_category, name="category"),
    path("name/<str:name>/", views.food_by_name, name="name"),

    # Add a food without requiring a category ID in the URL.
    path("add/", views.create_food_view, name="add"),

    # Keep the category-specific route for existing links.
    path("add/<int:category_id>/", views.create_food_view, name="add_to_category",
    ),
    path("edit/<int:food_id>/", views.edit_food_view, name="edit"),
    path("archive/<int:food_id>/", views.archive_food_view, name="archive"),
]