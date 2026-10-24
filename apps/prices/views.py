from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from services.foods import (
    get_all_foods,
    get_food_by_id,
)

from .models import PriceEntry


# =========================================================
# PRICE LIBRARY
# =========================================================

@login_required
def price_list(request):
    """
    Display the user's recorded food prices.
    """

    price_entries = PriceEntry.objects.filter(
        user=request.user
    ).select_related("food")

    food_id = request.GET.get("food")

    if food_id:
        price_entries = price_entries.filter(
            food_id=food_id
        )

    foods = get_all_foods()

    return render(
        request,
        "prices/price.html",
        {
            "price_entries": price_entries,
            "foods": foods,
            "selected_food": food_id,
        }
    )


# =========================================================
# ADD PRICE
# =========================================================

@login_required
def add_price(request):
    """
    Record a new food price.
    """

    if request.method == "POST":

        food_id = request.POST.get("food_id")
        price = request.POST.get("price")
        quantity = request.POST.get("quantity")
        unit = request.POST.get("unit")
        source = request.POST.get("source", "").strip()

        try:
            food = get_food_by_id(food_id)

            if food is None:
                raise ValueError(
                    "Choose a food from the list."
                )

            price = Decimal(price)
            quantity = Decimal(quantity)

            if price <= 0:
                raise ValueError(
                    "Enter a price greater than zero."
                )

            if quantity <= 0:
                raise ValueError(
                    "Enter a quantity greater than zero."
                )

            if not unit:
                raise ValueError(
                    "Choose a unit for this price."
                )

            PriceEntry.objects.create(
                user=request.user,
                food=food,
                price=price,
                quantity=quantity,
                unit=unit,
                source=source,
            )

            messages.success(
                request,
                f"Price for {food.name} recorded."
            )

            return redirect(
                "prices:list"
            )

        except (
            InvalidOperation,
            TypeError,
            ValueError
        ) as error:

            messages.error(
                request,
                str(error)
            )

    foods = get_all_foods()

    return render(
        request,
        "prices/price.html",
        {
            "foods": foods,
            "unit_choices": PriceEntry.UnitChoices.choices,
        }
    )


# =========================================================
# PRICE DETAIL
# =========================================================

@login_required
def price_detail(request, price_id):
    """
    Display a specific price entry belonging to the user.
    """

    price_entry = PriceEntry.objects.filter(
        id=price_id,
        user=request.user
    ).select_related(
        "food"
    ).first()

    if price_entry is None:
        return render(
            request,
            "prices/not_found.html",
            status=404
        )

    return render(
        request,
        "prices/price.html",
        {
            "price_entry": price_entry,
        }
    )


# =========================================================
# FOOD PRICE HISTORY
# =========================================================

@login_required
def food_price_history(request, food_id):
    """
    Display price history for one food.
    """

    food = get_food_by_id(food_id)

    if food is None:
        return render(
            request,
            "prices/price.html",
            status=404
        )

    price_entries = PriceEntry.objects.filter(
        user=request.user,
        food=food
    ).order_by(
        "-recorded_at"
    )

    return render(
        request,
        "prices/price.html",
        {
            "food": food,
            "price_entries": price_entries,
        }
    )