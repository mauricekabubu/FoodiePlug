from decimal import Decimal, InvalidOperation
from datetime import datetime

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.shortcuts import redirect, render
from urllib.parse import urlencode

from apps.foods.models import Food

from services.pantry import (
    get_user_pantry,
    get_pantry_item,
    add_to_pantry,
    update_pantry_item,
    update_quantity,
    remove_from_pantry,
    consume_from_pantry,
    get_expiring_items,
    get_expired_items,
    get_running_low_items,
    get_pantry_item_status,
)
from services.pagination import paginate_queryset


# =========================================================
# HELPERS
# =========================================================

def _parse_decimal(value, field_name="quantity"):
    """
    Convert a form value to Decimal.
    """

    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.")

    if value <= 0:
        raise ValueError(
            f"{field_name.capitalize()} must be greater than zero."
        )

    return value


def _parse_optional_decimal(value, field_name):
    """
    Convert an optional form value to Decimal.

    Empty values become zero.
    """

    if value in (None, ""):
        return Decimal("0")

    try:
        value = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"Enter a valid {field_name}.")

    if value < 0:
        raise ValueError(
            f"{field_name.capitalize()} cannot be negative."
        )

    return value


def _parse_date(value):
    """
    Convert an HTML date input into a Python date.
    """

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        raise ValueError("Enter a valid date.")
        

from django.utils import timezone

EXPIRING_SOON_DAYS = 3


def _annotate_item(item):
    """Attach display-only attributes the template expects."""
    item.status = get_pantry_item_status(item)

    food = item.food
    category = getattr(food, "category", None)
    item.category_key = str(category.id) if category else "uncategorised"
    item.category_label = category.name if category else "Uncategorised"

    image = getattr(food, "image", None)
    item.image_url = image.url if image else ""

    item.expiry_state = ""
    item.expiry_label = ""
    if item.expires_at:
        days_left = (item.expires_at - timezone.localdate()).days
        if days_left < 0:
            item.expiry_state = "expired"
            item.expiry_label = "Expired"
        elif days_left <= EXPIRING_SOON_DAYS:
            item.expiry_state = "soon"
            item.expiry_label = (
                "Expires today" if days_left == 0
                else "Expires tomorrow" if days_left == 1
                else f"Expires in {days_left} days"
            )
        else:
            item.expiry_label = f"Expires {item.expires_at:%d %b}"


# =========================================================
# PANTRY DASHBOARD
# =========================================================

@login_required
def pantry(request):
    """
    Display the user's pantry dashboard.
    """

    pantry_queryset = get_user_pantry(request.user)
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "all")
    if status not in {"all", "available", "low", "out"}:
        status = "all"
    category_id = request.GET.get("category", "all")
    sort = request.GET.get("sort", "expiry")
    if sort not in {"recent", "name", "quantity", "expiry", "category", "low"}:
        sort = "expiry"

    if query:
        pantry_queryset = pantry_queryset.filter(
            Q(food__name__icontains=query)
            | Q(food__category__name__icontains=query)
            | Q(unit__icontains=query)
        )
    if category_id != "all":
        if category_id.isdigit():
            pantry_queryset = pantry_queryset.filter(food__category_id=int(category_id))
        else:
            category_id = "all"

    if status == "out":
        pantry_queryset = pantry_queryset.filter(quantity__lte=0)
    elif status == "low":
        pantry_queryset = pantry_queryset.filter(
            minimum_quantity__gt=0,
            quantity__gt=0,
            quantity__lte=F("minimum_quantity"),
        )
    elif status == "available":
        pantry_queryset = pantry_queryset.filter(quantity__gt=0).filter(
            Q(minimum_quantity__lte=0)
            | Q(quantity__gt=F("minimum_quantity"))
        )

    orderings = {
        "recent": ("-created_at", "-pk"),
        "name": ("food__name", "pk"),
        "quantity": ("quantity", "pk"),
        "expiry": ("expires_at", "food__name", "pk"),
        "category": ("food__category__name", "food__name", "pk"),
    }
    if sort == "low":
        pantry_queryset = pantry_queryset.annotate(
            low_first=Case(
                When(
                    minimum_quantity__gt=0,
                    quantity__gt=0,
                    quantity__lte=F("minimum_quantity"),
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("low_first", "food__name", "pk")
    else:
        pantry_queryset = pantry_queryset.order_by(*orderings[sort])

    pantry_count = get_user_pantry(request.user).count()
    result_count = pantry_queryset.count()
    pagination = paginate_queryset(request, pantry_queryset, 20)
    pantry_items = list(pagination["page_obj"].object_list)

    expiring_items = get_expiring_items(
        request.user
    )

    expired_items = get_expired_items(
        request.user
    )

    running_low_items = get_running_low_items(
        request.user
    )

    # -----------------------------------------------------
    # Add calculated status information to each item
    # -----------------------------------------------------

    for item in pantry_items:        
        _annotate_item(item)

    # ...summary unchanged...

    # -----------------------------------------------------
    # Summary
    # -----------------------------------------------------

    total_items = pantry_count

    summary = {
        "total_items": total_items,
        "running_low": running_low_items.count(),
        "expiring_soon": expiring_items.count(),
        "estimated_value": Decimal("0"),
    }

    # -----------------------------------------------------
    # Food categories
    # -----------------------------------------------------

    category_params = request.GET.copy()
    category_params.pop("page", None)
    categories = []
    for key, label in [("all", "All")] + list(
        get_user_pantry(request.user)
        .values_list("food__category_id", "food__category__name")
        .distinct()
        .order_by("food__category__name")
    ):
        params = category_params.copy()
        if key == "all":
            params.pop("category", None)
        else:
            params["category"] = str(key)
        categories.append({
            "key": str(key),
            "label": label,
            "query": urlencode(params),
        })

    # -----------------------------------------------------
    # Foods for add form
    # -----------------------------------------------------

    foods = Food.objects.filter(
        is_active=True
    ).select_related(
        "category"
    ).order_by(
        "name", "pk"
    )

    # -----------------------------------------------------
    # Context
    # -----------------------------------------------------

    context = {
        "pantry_items": pantry_items,
        "pantry_count": pantry_count,
        "result_count": result_count,
        "page_obj": pagination["page_obj"],
        "page_links": pagination["page_links"],
        "page_query": pagination["page_query"],
        "pagination_label": "Pantry pages",
        "query": query,
        "status_filter": status,
        "selected_category": category_id,
        "sort": sort,
        "foods": foods,

        "expiring_items": expiring_items,
        "expired_items": expired_items,
        "running_low_items": running_low_items,

        "summary": summary,
        "categories": categories,

        # These will be expanded later when
        # meal/pantry intelligence is implemented.
        "insights": [],
        "cook_suggestions": [],
    }

    return render(
        request,
        "pantry/pantry.html",
        context
    )


# =========================================================
# ADD FOOD
# =========================================================

@login_required
def add_pantry_item(request):
    """
    Add a food item to the user's pantry.
    """

    if request.method != "POST":
        return redirect(
            "pantry:pantry"
        )

    try:
        # -------------------------------------------------
        # Food
        # -------------------------------------------------

        food_id = request.POST.get("food_id")

        if not food_id:
            raise ValueError(
                "Food is required."
            )

        food = Food.objects.filter(
            id=food_id,
            is_active=True
        ).first()

        if food is None:
            raise ValueError(
                "The selected food could not be found."
            )

        # -------------------------------------------------
        # Quantity
        # -------------------------------------------------

        quantity = _parse_decimal(
            request.POST.get("quantity"),
            "quantity"
        )

        # -------------------------------------------------
        # Unit
        # -------------------------------------------------

        unit = request.POST.get(
            "unit"
        )

        if not unit:
            raise ValueError(
                "Unit is required."
            )

        # -------------------------------------------------
        # Minimum quantity
        # -------------------------------------------------

        minimum_quantity = _parse_optional_decimal(
            request.POST.get("minimum_quantity"),
            "minimum quantity"
        )

        # -------------------------------------------------
        # Storage
        # -------------------------------------------------

        storage = request.POST.get(
            "storage",
            "pantry"
        )

        # -------------------------------------------------
        # Dates
        # -------------------------------------------------

        acquired_at = _parse_date(
            request.POST.get("acquired_at")
        )

        expires_at = _parse_date(
            request.POST.get("expires_at")
        )

        # -------------------------------------------------
        # Notes
        # -------------------------------------------------

        notes = request.POST.get(
            "notes",
            ""
        ).strip()

        # -------------------------------------------------
        # Create / update pantry item
        # -------------------------------------------------

        pantry_item = add_to_pantry(
            user=request.user,
            food=food,
            quantity=quantity,
            unit=unit,
            minimum_quantity=minimum_quantity,
            storage=storage,
            acquired_at=acquired_at,
            expires_at=expires_at,
            notes=notes,
        )

        messages.success(
            request,
            f"{food.name} added to your pantry."
        )
        
        return redirect("pantry:pantry")

    except (ValueError, TypeError) as error:

        messages.error(
            request,
            str(error)
        )

    return redirect(
        "pantry:pantry"
    )


# =========================================================
# PANTRY ITEM DETAIL
# =========================================================

@login_required
def pantry_item_detail(request, item_id):
    """
    Display the details of a pantry item.
    """

    pantry_item = get_pantry_item(
        request.user,
        item_id
    )

    if pantry_item is None:

        messages.error(
            request,
            "The requested pantry item could not be found."
        )

        return redirect(
            "pantry:pantry"
        )

    pantry_item.status = get_pantry_item_status(
        pantry_item
    )

    return render(
        request,
        "pantry/pantry_item_detail.html",
        {
            "pantry_item": pantry_item,
        }
    )


# =========================================================
# UPDATE PANTRY ITEM
# =========================================================

@login_required
def update_pantry_item_view(request, item_id):
    """
    Update a pantry item's details.
    """

    if request.method != "POST":
        return redirect(
            "pantry:pantry"
        )

    try:

        pantry_item = get_pantry_item(
            request.user,
            item_id
        )

        if pantry_item is None:
            raise ValueError(
                "The pantry item could not be found."
            )

        quantity = _parse_decimal(
            request.POST.get("quantity"),
            "quantity"
        )

        minimum_quantity = _parse_optional_decimal(
            request.POST.get("minimum_quantity"),
            "minimum quantity"
        )

        unit = request.POST.get(
            "unit"
        )

        storage = request.POST.get(
            "storage"
        )

        acquired_at = _parse_date(
            request.POST.get("acquired_at")
        )

        expires_at = _parse_date(
            request.POST.get("expires_at")
        )

        notes = request.POST.get(
            "notes",
            ""
        ).strip()

        update_pantry_item(
            user=request.user,
            pantry_item_id=item_id,
            quantity=quantity,
            unit=unit,
            minimum_quantity=minimum_quantity,
            storage=storage,
            acquired_at=acquired_at,
            expires_at=expires_at,
            notes=notes,
        )

        messages.success(
            request,
            "Your pantry item has been updated."
        )

    except (ValueError, TypeError) as error:

        messages.error(
            request,
            str(error)
        )

    return redirect(
        "pantry:pantry"
    )


# =========================================================
# UPDATE QUANTITY
# =========================================================

@login_required
def update_pantry_quantity(request, item_id):
    """
    Update only the quantity of a pantry item.
    """

    if request.method != "POST":
        return redirect(
            "pantry:pantry"
        )

    try:

        quantity = _parse_decimal(
            request.POST.get("quantity"),
            "quantity"
        )

        pantry_item = update_quantity(
            request.user,
            item_id,
            quantity
        )

        if pantry_item is None:

            messages.error(
                request,
                "The pantry item could not be found."
            )

        else:

            messages.success(
                request,
                "Pantry item quantity updated."
            )

    except (ValueError, TypeError) as error:

        messages.error(
            request,
            str(error)
        )

    return redirect(
        "pantry:pantry"
    )


# =========================================================
# REMOVE ITEM
# =========================================================

@login_required
def remove_pantry_item(request, item_id):
    """
    Remove a pantry item completely.
    """

    if request.method != "POST":
        return redirect(
            "pantry:pantry"
        )

    removed = remove_from_pantry(
        request.user,
        item_id
    )

    if removed:

        messages.success(
            request,
            "Pantry item removed."
        )

    else:

        messages.error(
            request,
            "The pantry item could not be found."
        )

    return redirect(
        "pantry:pantry"
    )


# =========================================================
# CONSUME FOOD
# =========================================================

@login_required
def consume_pantry_item(request, item_id):
    """
    Consume part of a pantry item.
    """

    if request.method != "POST":
        return redirect(
            "pantry:pantry"
        )

    try:

        quantity = _parse_decimal(
            request.POST.get("quantity"),
            "quantity"
        )

        pantry_item = consume_from_pantry(
            request.user,
            item_id,
            quantity
        )

        if pantry_item is None:

            messages.success(
                request,
                "Pantry item consumed."
            )

        else:

            messages.success(
                request,
                "Pantry quantity updated."
            )

    except (ValueError, TypeError) as error:

        messages.error(
            request,
            str(error)
        )

    return redirect(
        "pantry:pantry"
    )


# =========================================================
# EXPIRING ITEMS
# =========================================================

@login_required
def expiring_items(request):
    """
    Display pantry items that are expiring soon.
    """

    days = request.GET.get(
        "days",
        3
    )

    try:

        days = int(days)

        if days <= 0:
            raise ValueError

    except (TypeError, ValueError):

        messages.error(
            request,
            "Please enter a valid number of days."
        )

        return redirect(
            "pantry:pantry"
        )

    items = get_expiring_items(
        request.user,
        days=days
    )

    return render(
        request,
        "pantry/expiring.html",
        {
            "expiring_items": items,
            "days": days,
        }
    )


# =========================================================
# EXPIRED ITEMS
# =========================================================

@login_required
def expired_items(request):
    """
    Display pantry items that have expired.
    """

    items = get_expired_items(
        request.user
    )

    return render(
        request,
        "pantry/expired.html",
        {
            "expired_items": items,
        }
    )