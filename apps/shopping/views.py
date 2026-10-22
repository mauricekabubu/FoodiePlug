from urllib.parse import urlencode
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme

from services.shopping import (
    create_shopping_list,
    get_user_shopping_lists,
    get_shopping_list,
    rename_shopping_list,
    delete_shopping_list,
    add_shopping_item,
    update_shopping_item,
    remove_shopping_item,
    mark_item_purchased,
    mark_item_unpurchased,
    get_shopping_list_progress,
)
from apps.foods.models import Food

logger = logging.getLogger(__name__)


# =========================================================
# HELPERS
# =========================================================

def _back_to_list(request, list_id=None):
    """
    Redirect to a list's detail page.

    Falls back to the lists page if the id is missing or invalid, so a
    missing hidden `list_id` can never cause a NoReverseMatch crash.
    """
    list_id = list_id if list_id is not None else request.POST.get("list_id")

    try:
        list_id = int(list_id)
    except (TypeError, ValueError):
        return redirect("shopping_lists")

    return redirect("shopping_list_detail", list_id=list_id)


# =========================================================
# SHOPPING LIST PAGES
# =========================================================

@login_required
def shopping_lists(request):
    """Display all shopping lists for the logged-in user."""

    lists = get_user_shopping_lists(request.user)

    # The template shows an item count per list; prefetch to avoid N+1 queries.
    if hasattr(lists, "prefetch_related"):
        lists = lists.prefetch_related("items")

    return render(request, "shopping/shopping.html", {"shopping_lists": lists})


@login_required
def shopping_list_detail(request, list_id):
    """Display one shopping list with its items."""

    try:
        shopping_list = get_shopping_list(request.user, list_id)
        progress = get_shopping_list_progress(request.user, list_id)

    except ValueError:
        messages.error(request, "That shopping list couldn't be found.")
        return redirect("shopping_lists")

    items = shopping_list.items.select_related("food", "food__category")

    foods = Food.objects.filter(
        is_active=True
    ).select_related(
        "category"
    ).order_by("name")

    return render(request, "shopping/shopping.html", {
        "shopping_list": shopping_list,
        "items": items,
        "foods": foods,
        "progress": progress,
    })


@login_required
def create_list(request):
    """Create a new shopping list."""

    if request.method != "POST":
        return redirect("shopping_lists")

    name = request.POST.get("name", "").strip() or "Shopping List"

    try:
        new_list = create_shopping_list(request.user, name)
        messages.success(request, f"Your shopping list “{new_list.name}” is ready.")
        return redirect("shopping_list_detail", list_id=new_list.id)

    except ValueError:
        messages.error(request, "We couldn't create that shopping list. Please try again.")

    return redirect("shopping_lists")


@login_required
def rename_list(request, list_id):
    """Rename an existing shopping list."""

    if request.method == "POST":
        new_name = request.POST.get("name", "").strip()

        try:
            rename_shopping_list(request.user, list_id, new_name)
            messages.success(request, "Your shopping list name has been updated.")
        except ValueError:
            messages.error(request, "Enter a name for your shopping list.")

    return redirect("shopping_list_detail", list_id=list_id)


@login_required
def delete_list(request, list_id):
    """Delete a shopping list."""

    if request.method == "POST":
        try:
            delete_shopping_list(request.user, list_id)
            messages.success(request, "Your shopping list has been deleted.")
            return redirect("shopping_lists")
        except ValueError:
            messages.error(request, "We couldn't delete that shopping list. Please try again.")

    return redirect("shopping_list_detail", list_id=list_id)


# =========================================================
# SHOPPING ITEM ACTIONS
# =========================================================

@login_required
def add_item(request, list_id):
    """Add an item to a shopping list."""

    if request.method != "POST":
        messages.error(request, "To add an item, use the form on your shopping list.")
        return redirect("shopping_list_detail", list_id=list_id)

    food_id = request.POST.get("food_id")
    quantity = request.POST.get("quantity")
    unit = request.POST.get("unit")

    try:
        add_shopping_item(request.user, list_id, food_id, quantity, unit)
        messages.success(request, "Item added to your shopping list.")
    except ValueError:
        messages.error(request, "We couldn't add that item. Check its details and try again.")

    return redirect("shopping_list_detail", list_id=list_id)


@login_required
def update_item(request, item_id):
    """Update a shopping item's quantity and unit."""

    if request.method == "POST":
        quantity = request.POST.get("quantity")
        unit = request.POST.get("unit")

        try:
            update_shopping_item(request.user, item_id, quantity, unit)
            messages.success(request, "Your shopping list item has been updated.")
        except ValueError:
            messages.error(request, "We couldn't update that item. Check the quantity and unit.")

    return _back_to_list(request)


@login_required
def remove_item(request, item_id):
    """Remove an item from a shopping list."""

    if request.method == "POST":
        try:
            remove_shopping_item(request.user, item_id)
            messages.success(request, "Item removed from your shopping list.")
        except ValueError:
            messages.error(request, "We couldn't remove that item. Refresh the list and try again.")

    return _back_to_list(request)


# =========================================================
# PURCHASE ACTIONS
# =========================================================

@login_required
def purchase_item(request, item_id):
    """Mark a shopping item as purchased."""

    if request.method == "POST":
        try:
            mark_item_purchased(request.user, item_id)
            messages.success(request, "Marked as purchased.")
        except ValueError:
            messages.error(request, "We couldn't update that item. Refresh the list and try again.")

    return _back_to_list(request)


@login_required
def unpurchase_item(request, item_id):
    """Mark a shopping item as not purchased."""

    if request.method == "POST":
        try:
            mark_item_unpurchased(request.user, item_id)
            messages.success(request, "Marked as not purchased.")
        except ValueError:
            messages.error(request, "We couldn't update that item. Refresh the list and try again.")

    return _back_to_list(request)


# =====================================================================
# SHOPPING LIST MANAGEMENT — changes to apps/shopping/views.py
#
# 1. Add these imports (keep your existing ones):
#
#        from django.core.paginator import Paginator
#        from django.db.models import Count, Q
#        from django.db.models.functions import Lower
#        from django.urls import reverse
#        from django.utils.http import url_has_allowed_host_and_scheme, urlencode
#
# 2. REPLACE `shopping_lists`, `rename_list` and `delete_list` with the versions below
#    (based on the views you shared; compare with your current file before pasting).
# 3. ADD `archive_list`, `restore_list` and the helpers.
#
# Assumptions to check:
#   * get_user_shopping_lists(user) returns a QuerySet of that user's lists (it needs
#     .annotate / .filter, and items are reachable as `items`).
#   * Archiving needs a boolean `is_archived` on the list model (see the note at the end).
#     Without it the Archive menu items and tabs are hidden and the archive views refuse.
# =====================================================================

LISTS_PER_PAGE = 12
MAX_SEARCH_CHARS = 100

SORT_OPTIONS = [
    ("updated", "Recently updated"),
    ("name", "Name A–Z"),
    ("name_desc", "Name Z–A"),
]
SORT_KEYS = {key for key, _label in SORT_OPTIONS}


# =========================================================
# HELPERS
# =========================================================

def _safe_next(request, default):
    """
    Where to go after a POST. Only same-site URLs are accepted, so a crafted `next`
    value can't send the user to another website.
    """
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return target
    return default


def _model_fields(queryset):
    return {field.name for field in queryset.model._meta.get_fields()}


def _order_by(sort, fields):
    """Ordering that uses whichever date field the model really has."""
    if sort == "name":
        return [Lower("name").asc(), "id"]
    if sort == "name_desc":
        return [Lower("name").desc(), "-id"]

    date_field = "updated_at" if "updated_at" in fields else "created_at" if "created_at" in fields else "id"
    return [f"-{date_field}", "-id"]


def _page_links(page_obj):
    """Page numbers with gaps for long lists: 1 … 4 5 [6] 7 8 … 20."""
    paginator = page_obj.paginator
    elided = getattr(paginator, "get_elided_page_range", None)      # Django 3.2+
    numbers = elided(page_obj.number, on_each_side=1, on_ends=1) if elided else paginator.page_range
    return [{"number": n, "current": n == page_obj.number, "gap": not isinstance(n, int)} for n in numbers]


# =========================================================
# LISTS INDEX  (replaces the existing view)
# =========================================================

@login_required
def shopping_lists(request):
    """The user's shopping lists: search, sort, active/archived, 12 per page."""

    # Scoped to the signed-in user by the service. prefetch_related(None) drops any prefetch
    # the service adds: the cards only need counts, which are computed in the same query.
    base = get_user_shopping_lists(request.user).prefetch_related(None)
    fields = _model_fields(base)

    archive_enabled = "is_archived" in fields
    status = request.GET.get("status", "active")
    if status != "archived" or not archive_enabled:
        status = "active"

    q = request.GET.get("q", "").strip()[:MAX_SEARCH_CHARS]
    sort = request.GET.get("sort", "updated")
    if sort not in SORT_KEYS:
        sort = "updated"

    active_count = archived_count = None
    scoped = base
    if archive_enabled:
        totals = base.aggregate(
            active=Count("id", filter=Q(is_archived=False)),
            archived=Count("id", filter=Q(is_archived=True)),
        )
        active_count, archived_count = totals["active"], totals["archived"]
        scoped = base.filter(is_archived=(status == "archived"))

    if archive_enabled:
        user_total = active_count if status == "active" else archived_count
    else:
        user_total = scoped.count()

    results = scoped.filter(name__icontains=q) if q else scoped
    results = (
        results
        .annotate(
            item_total=Count("items", distinct=True),
            purchased_total=Count("items", filter=Q(items__is_purchased=True), distinct=True),
        )
        .order_by(*_order_by(sort, fields))
    )

    paginator = Paginator(results, LISTS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))         # bad/out-of-range pages are corrected

    # Query string that keeps the filters while paging (the template adds &page=N).
    params = {}
    if q:
        params["q"] = q
    if sort != "updated":
        params["sort"] = sort
    if status == "archived":
        params["status"] = "archived"

    clear_params = {k: v for k, v in params.items() if k != "q"}

    return render(request, "shopping/shopping.html", {
        "shopping_lists": page_obj.object_list,
        "page_obj": page_obj,
        "page_links": _page_links(page_obj),
        "total_count": paginator.count,
        "user_total": user_total,
        "q": q,
        "sort": sort,
        "sort_options": SORT_OPTIONS,
        "status": status,
        "archive_enabled": archive_enabled,
        "active_count": active_count,
        "archived_count": archived_count,
        "base_qs": urlencode(params),
        "clear_search_qs": urlencode(clear_params),
        "return_to": request.get_full_path(),                     # modals send the user back here
    })


# =========================================================
# RENAME / DELETE  (same services and validation; they now honour a same-site `next`)
# =========================================================

@login_required
def rename_list(request, list_id):
    """Rename an existing shopping list."""

    if request.method == "POST":
        new_name = request.POST.get("name", "").strip()

        try:
            rename_shopping_list(request.user, list_id, new_name)
            messages.success(request, "Your shopping list name has been updated.")
        except ValueError:
            messages.error(request, "Enter a name for your shopping list.")

    default = reverse("shopping_list_detail", args=[list_id])
    return redirect(_safe_next(request, default))


@login_required
def delete_list(request, list_id):
    """Delete a shopping list (POST only)."""

    if request.method == "POST":
        try:
            delete_shopping_list(request.user, list_id)
            messages.success(request, "Your shopping list has been deleted.")
            return redirect(_safe_next(request, reverse("shopping_lists")))
        except ValueError:
            messages.error(request, "We couldn't delete that shopping list. Please try again.")

    # GET, or a failed delete: nothing was removed.
    default = reverse("shopping_list_detail", args=[list_id])
    return redirect(_safe_next(request, default))


# =========================================================
# ARCHIVE / RESTORE  (nothing is deleted; items and purchase history stay as they are)
# =========================================================

def _set_archived(request, list_id, archived):
    fallback = reverse("shopping_lists")

    if request.method != "POST":
        return redirect(fallback)

    target = _safe_next(request, fallback)

    try:
        shopping_list = get_shopping_list(request.user, list_id)      # raises ValueError if it isn't theirs
    except ValueError:
        messages.error(request, "That shopping list couldn't be found.")
        return redirect(target)

    if not hasattr(shopping_list, "is_archived"):
        messages.error(request, "This shopping list can't be archived right now.")
        return redirect(target)

    try:
        shopping_list.is_archived = archived
        shopping_list.save(update_fields=["is_archived"])
    except Exception:
        logger.exception(
            "Could not update archive status for shopping list %s and user %s",
            list_id,
            request.user.pk,
        )
        messages.error(request, "We couldn't update that list. Please try again.")
        return redirect(target)

    if archived:
        messages.success(request, f"“{shopping_list.name}” was moved to your archive.")
    else:
        messages.success(request, f"“{shopping_list.name}” was restored.")
    return redirect(target)


@login_required
def archive_list(request, list_id):
    """Move a list to the archive. POST only."""
    return _set_archived(request, list_id, True)


@login_required
def restore_list(request, list_id):
    """Bring an archived list back. POST only."""
    return _set_archived(request, list_id, False)


# ---------------------------------------------------------------------
# Archive needs one model field (then `makemigrations` and `migrate`):
#
#     is_archived = models.BooleanField(default=False, db_index=True)
#
# default=False keeps every existing list visible. The detail page, items, purchase state
# and prices are untouched by archiving. Other places that call get_user_shopping_lists()
# (dashboard, insights, AI tools) don't know about archiving yet and will still include
# archived lists; filter them there if you want them hidden everywhere.
# ---------------------------------------------------------------------