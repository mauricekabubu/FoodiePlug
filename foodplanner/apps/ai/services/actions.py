"""
apps/ai/services/actions.py — changes the AI can ask for, and how they actually happen.

The model can never write to the database. It can only call propose_* (see tools.py), which
validates the request and parks it as a *pending action* with a one-time id. Nothing changes
until the signed-in user confirms that id through confirm_action(), normally from a Confirm
button in the chat UI:

    POST /ai/actions/<id>/confirm/   ->  confirm_action(request.user, id)
    POST /ai/actions/<id>/cancel/    ->  cancel_action(request.user, id)

Pending actions live in the cache (15 minutes), are tied to the user who triggered them, can be
confirmed once, and are re-validated at confirmation time. Execution goes through the same
services the rest of FoodiePlug uses, so existing business rules still apply.
"""

import logging
import secrets
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.utils import timezone

from services.foods import get_food_by_id
from services.meals import get_user_available_meal, schedule_meal
from services.shopping import add_shopping_item, create_shopping_list, get_user_shopping_lists
from services.timetable import MEAL_TYPES

logger = logging.getLogger(__name__)

PENDING_TTL_SECONDS = 15 * 60
MAX_ITEMS_PER_PROPOSAL = 25
MAX_QUANTITY = Decimal("100000")
MAX_SERVINGS = 50
MAX_DAYS_AHEAD = 365
DEFAULT_LIST_NAME = "FoodiePlug AI list"

# Keep in step with the unit list used by the meal ingredient form.
ALLOWED_UNITS = ("g", "kg", "ml", "l", "piece", "bunch", "packet")


class ActionError(ValueError):
    """Validation problem. The message is written for the model and is safe to show the user."""


@dataclass
class ActionResult:
    ok: bool
    message: str
    details: dict = field(default_factory=dict)


# =========================================================
# PENDING STORE
# =========================================================

def _key(action_id):
    return f"ai:pending:{action_id}"


def _park(user, kind, params, summary):
    action_id = secrets.token_urlsafe(16)
    cache.set(
        _key(action_id),
        {"user_id": user.pk, "kind": kind, "params": params, "summary": summary,
         "created": timezone.now().isoformat(timespec="seconds")},
        timeout=PENDING_TTL_SECONDS,
    )
    return {
        "id": action_id,
        "kind": kind,
        "summary": summary,
        "expires_in_minutes": PENDING_TTL_SECONDS // 60,
    }


def get_pending(user, action_id):
    """The pending action, but only for the user who triggered it."""
    if not isinstance(action_id, str) or len(action_id) > 64:
        return None
    record = cache.get(_key(action_id))
    if not record or record.get("user_id") != user.pk:
        return None
    return record


def cancel_action(user, action_id):
    if get_pending(user, action_id) is None:
        return False
    cache.delete(_key(action_id))
    return True


# =========================================================
# VALIDATION HELPERS
# =========================================================

def _quantity(value):
    try:
        qty = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ActionError("Quantity must be a number such as 2 or 0.5.")
    if not qty.is_finite() or qty <= 0 or qty > MAX_QUANTITY:
        raise ActionError("Quantity must be greater than zero and reasonable.")
    return qty.quantize(Decimal("0.01"))


def _unit(value):
    unit = str(value or "").strip().lower()
    if unit not in ALLOWED_UNITS:
        raise ActionError(f"Unit must be one of: {', '.join(ALLOWED_UNITS)}.")
    return unit


def _fmt(qty):
    text = format(qty, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _list_name(value):
    name = " ".join(str(value or "").split())[:80]
    return name or DEFAULT_LIST_NAME


# =========================================================
# PROPOSALS (called by the propose_* tools)
# =========================================================

def propose_shopping_items(user, items, list_name=None):
    if not isinstance(items, list) or not items:
        raise ActionError("Provide at least one item to add.")
    if len(items) > MAX_ITEMS_PER_PROPOSAL:
        raise ActionError(f"Please propose at most {MAX_ITEMS_PER_PROPOSAL} items at a time.")

    merged = {}                                     # (food_id, unit) -> {"food", "quantity"}
    for entry in items:
        if not isinstance(entry, dict):
            raise ActionError("Each item needs a food_id, quantity and unit.")

        try:
            food_id = int(entry.get("food_id"))
        except (TypeError, ValueError, InvalidOperation):
            raise ActionError("Each item needs a numeric food_id from the food library. Use search_foods first.")

        food = get_food_by_id(food_id)
        if food is None:
            raise ActionError(f"Food {food_id} was not found in the food library.")

        qty, unit = _quantity(entry.get("quantity")), _unit(entry.get("unit"))
        slot = merged.setdefault((food.id, unit), {"food": food, "quantity": Decimal("0")})
        slot["quantity"] += qty

    name = _list_name(list_name)
    existing = next((l for l in get_user_shopping_lists(user) if l.name.lower() == name.lower()), None)

    lines = [f"{_fmt(v['quantity'])} {unit} {v['food'].name}" for (_fid, unit), v in merged.items()]
    target = f"your list “{existing.name}”" if existing else f"a new list “{name}”"
    summary = f"Add to {target}: " + "; ".join(lines)

    params = {
        "list_name": existing.name if existing else name,
        "items": [{"food_id": fid, "unit": unit, "quantity": str(v["quantity"])}
                  for (fid, unit), v in merged.items()],
    }
    return _park(user, "add_shopping_items", params, summary)


def propose_schedule_meal(user, meal_id, day, meal_type, servings=1):
    try:
        meal = get_user_available_meal(user, int(meal_id))
    except (TypeError, ValueError):
        meal = None
    if meal is None:
        raise ActionError("That meal was not found. Use search_meals to find its id.")

    try:
        target_day = date.fromisoformat(str(day))
    except ValueError:
        raise ActionError("The date must look like 2026-10-14.")

    today = timezone.localdate()
    if target_day < today:
        raise ActionError("That date has already passed.")
    if (target_day - today).days > MAX_DAYS_AHEAD:
        raise ActionError("That date is too far ahead.")

    if meal_type not in MEAL_TYPES:
        raise ActionError(f"meal_type must be one of: {', '.join(MEAL_TYPES)}.")

    try:
        servings_value = Decimal(str(servings))
    except (TypeError, ValueError, InvalidOperation):
        raise ActionError("Servings must be a whole number.")
    if not servings_value.is_finite() or servings_value != servings_value.to_integral_value():
        raise ActionError("Servings must be a whole number.")
    servings = int(servings_value)
    if not 1 <= servings <= MAX_SERVINGS:
        raise ActionError(f"Servings must be between 1 and {MAX_SERVINGS}.")

    summary = f"Plan “{meal.name}” for {meal_type} on {target_day:%A %d %B}, {servings} serving{'s' if servings != 1 else ''}."
    params = {"meal_id": meal.id, "date": target_day.isoformat(), "meal_type": meal_type, "servings": servings}
    return _park(user, "schedule_meal", params, summary)


# =========================================================
# CONFIRMATION (called from a view, never by the model)
# =========================================================

def confirm_action(user, action_id):
    """Run a pending action for the user who owns it. One use only."""
    record = get_pending(user, action_id)
    if record is None:
        return ActionResult(False, "That request has expired or can't be found. Please ask again.")

    # Claim it first so a double click can't run it twice.
    if not cache.delete(_key(action_id)):
        return ActionResult(False, "That request was already handled.")

    try:
        if record["kind"] == "add_shopping_items":
            result = _run_shopping(user, record["params"])
        elif record["kind"] == "schedule_meal":
            result = _run_schedule(user, record["params"])
        else:
            result = ActionResult(False, "That kind of action isn't supported.")
    except ActionError as error:
        result = ActionResult(False, str(error))
    except Exception:
        logger.exception("AI action failed (kind=%s)", record.get("kind"))
        result = ActionResult(False, "Something went wrong and nothing was saved. Please try again.")

    logger.info("AI action %s user=%s ok=%s", record.get("kind"), user.pk, result.ok)
    return result


def _run_shopping(user, params):
    name = params["list_name"]
    target = next((l for l in get_user_shopping_lists(user) if l.name.lower() == name.lower()), None) \
        or create_shopping_list(user, name)

    added = skipped = 0
    for item in params["items"]:
        food = get_food_by_id(item["food_id"])            # may have been archived since the proposal
        if food is None:
            skipped += 1
            continue
        try:
            add_shopping_item(user, target.id, food.id, str(Decimal(item["quantity"]).quantize(Decimal("0.01"))), item["unit"])
            added += 1
        except ValueError:
            skipped += 1                                  # e.g. already on the list

    if not added:
        return ActionResult(False, "None of the items could be added (they may already be on the list).",
                            {"list": target.name})

    message = f"Added {added} item{'s' if added != 1 else ''} to “{target.name}”."
    if skipped:
        message += f" {skipped} skipped (already there or no longer available)."
    return ActionResult(True, message, {"list": target.name, "added": added, "skipped": skipped})


def _run_schedule(user, params):
    meal = get_user_available_meal(user, params["meal_id"])
    if meal is None:
        raise ActionError("That meal is no longer available.")

    try:
        schedule_meal(
            user=user,
            meal=meal,
            date=date.fromisoformat(params["date"]),
            meal_type=params["meal_type"],
            servings=params["servings"],
        )
    except ValueError as error:
        raise ActionError(str(error))
    return ActionResult(True, f"“{meal.name}” is now on your planner for {params['date']} ({params['meal_type']}).",
                        {"meal": meal.name, "date": params["date"]})