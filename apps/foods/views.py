import logging

from django.contrib.auth.decorators import login_required
from django.shortcuts import render ,get_object_or_404
from django.contrib import messages
from django.shortcuts import render, redirect
from datetime import datetime

from services.foods import (
    get_all_foods,
    get_food_by_id,
    get_food_by_name,
    search_foods,
    get_foods_by_category,
    get_all_categories,
    create_food,
    update_food, archive_food
)

from django.db import IntegrityError
from django.views.decorators.http import require_POST
from apps.foods.models import Food, FoodCategory
from services.pagination import paginate_queryset

logger = logging.getLogger(__name__)

# =========================================================
# FOOD LIBRARY
# =========================================================

@login_required
def food_library(request):
    """Display all active foods and available categories."""

    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category")

    if query:
        foods = search_foods(query)
        if category_id:
            foods = foods.filter(category_id=category_id)
    elif category_id:
        foods = get_foods_by_category(category_id)
    else:
        foods = get_all_foods()

    foods = foods.select_related("category").order_by("name", "pk")
    pagination = paginate_queryset(request, foods, 24)
    categories = get_all_categories()

    return render(
        request,
        "foods/library.html",
        {
            "foods": pagination["page_obj"].object_list,
            "page_obj": pagination["page_obj"],
            "page_links": pagination["page_links"],
            "page_query": pagination["page_query"],
            "total_count": pagination["page_obj"].paginator.count,
            "pagination_label": "Food library pages",
            "categories": categories,
            "query": query,
            "selected_category": category_id,
        }
    )
    
# =========================================================
# FOOD DETAIL
# =========================================================

@login_required
def food_detail(request, food_id):
    """Display details for one active food."""
    food = get_food_by_id(food_id)
    
    if not food:
        return render(request, "foods/library.html", {"food_id": food_id})
    
    return render(request, "foods/library.html", {"food": food})

# =========================================================
# FOOD SEARCH
# =========================================================

@login_required
def food_search(request):
    """Search the active food library."""

    query = request.GET.get("q", "").strip()

    foods = search_foods(query) if query else get_all_foods()
    foods = foods.select_related("category").order_by("name", "pk")
    pagination = paginate_queryset(request, foods, 24)

    categories = get_all_categories()

    return render(
        request,
        "foods/library.html",
        {
            "foods": pagination["page_obj"].object_list,
            "categories": categories,
            "query": query,
            "page_obj": pagination["page_obj"],
            "page_links": pagination["page_links"],
            "page_query": pagination["page_query"],
            "total_count": pagination["page_obj"].paginator.count,
            "pagination_label": "Food search pages",
        },
    )


# =========================================================
# FOOD CATEGORY
# =========================================================

@login_required
def food_category(request, category_id):
    """Display active foods belonging to a category."""

    foods = get_foods_by_category(category_id)
    foods = foods.select_related("category").order_by("name", "pk")
    pagination = paginate_queryset(request, foods, 24)
    categories = get_all_categories()

    return render(
        request,
        "foods/library.html",
        {
            "foods": pagination["page_obj"].object_list,
            "categories": categories,
            "selected_category": category_id,
            "page_obj": pagination["page_obj"],
            "page_links": pagination["page_links"],
            "page_query": pagination["page_query"],
            "total_count": pagination["page_obj"].paginator.count,
            "pagination_label": "Food category pages",
        },
    )
    

# =========================================================
# FOOD BY NAME
# =========================================================

@login_required
def food_by_name(request):
    """Find an active food by its exact name."""

    name = request.GET.get("name", "").strip()

    food = None

    if name:
        food = get_food_by_name(name)

    return render(
        request,
        "foods/by_name.html",
        {
            "food": food,
            "name": name,
        }
    )



@login_required
def create_food_view(request, category_id=None):
    """Create a food, optionally using a category supplied in the URL."""

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        selected_category = request.POST.get("category") or category_id
        default_unit = request.POST.get("default_unit", "").strip()
        is_perishable = request.POST.get("is_perishable") in (
            "on", "true", "True", "1"
        )
        shelf_life = request.POST.get("shelf_life") or None

        # Uploaded files are available through request.FILES.
        image = request.FILES.get("image") or request.POST.get("image")

        if not name:
            messages.error(request, "Enter a name for the food.")
            return redirect("foods:foods")

        if not selected_category:
            messages.error(request, "Choose a category for the food.")
            return redirect("foods:foods")

        if not default_unit:
            messages.error(request, "Choose a default unit for the food.")
            return redirect("foods:foods")

        try:
            
            created_food = create_food(
                name=name,
                category=selected_category,
                default_unit=default_unit,
                is_perishable=is_perishable,
                shelf_life=shelf_life,
                image=image,
            )

            if created_food:
                messages.success(request, "Food added to your library.")
            else:
                messages.error(request, "We couldn't add that food. Please try again.")

        except Exception:
            logger.exception("Could not create a food library entry.")
            messages.error(request, "We couldn't add that food. Please check the details and try again.")

        return redirect("foods:foods")

    return redirect("foods:foods")
        
            

@login_required
def edit_food_view(request, food_id):
    """Edit an active food."""

    food = get_object_or_404(
        Food,
        pk=food_id,
        is_active=True,
    )
    categories = get_all_categories()
    unit_choices = Food.UnitChoices.choices

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "").strip()
        default_unit = request.POST.get("default_unit", "").strip()
        is_perishable = request.POST.get("is_perishable") == "on"
        shelf_life = request.POST.get("shelf_life", "").strip()
        image = request.FILES.get("image")
        clear_image = request.POST.get("clear_image") == "on"

        valid_units = {value for value, label in unit_choices}
        category_exists = FoodCategory.objects.filter(
            pk=category
        ).exists() if category.isdigit() else False

        if not name:
            messages.error(request, "Food name is required.")
        elif not category_exists:
            messages.error(request, "Please select a valid category.")
        elif default_unit not in valid_units:
            messages.error(request, "Please select a valid unit.")
        elif shelf_life and (
            not shelf_life.isdigit() or int(shelf_life) < 0
        ):
            messages.error(request, "Shelf life must be zero or more days.")
        else:
            try:
                updated = update_food(
                    food_id=food.id,
                    name=name,
                    category=category,
                    default_unit=default_unit,
                    is_perishable=is_perishable,
                    shelf_life=shelf_life or None,
                    image=image,
                    clear_image=clear_image,
                )

                if updated:
                    messages.success(request, "Your food details have been saved.")
                    return redirect("foods:foods")

                messages.error(request, "This food is no longer active.")

            except IntegrityError:
                messages.error(
                    request,
                    "A food with that name already exists.",
                )
            except Exception:
                messages.error(
                    request,
                    "Could not update the food. Check the details and try again.",
                )

    return render(
        request,
        "foods/edit.html",
        {
            "food": food,
            "categories": categories,
            "unit_choices": unit_choices,
        },
    )


@login_required
@require_POST
def archive_food_view(request, food_id):
    """Archive a food without permanently deleting it."""

    if archive_food(food_id):
        messages.success(request, "Food moved to your archive.")
    else:
        messages.error(request, "That food could not be found in your active library.")

    return redirect("foods:foods")
