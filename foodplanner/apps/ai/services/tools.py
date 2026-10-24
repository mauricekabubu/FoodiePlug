"""
apps/ai/services/tools.py — what the model is allowed to look at or ask for.

Rules every tool follows (enforced here, not by the prompt):

  * The model never supplies a user id. Handlers receive the authenticated `user` from the
    server and call the existing FoodiePlug services with it, so every query is scoped to that user.
  * Each tool declares the data categories it touches. If the user switched a category off
    (safety.AIPermissions), the tool is hidden from the model AND refused at dispatch.
  * Arguments are validated; unknown arguments are ignored; errors come back as {"ok": False, ...}.
  * Output is trimmed and converted to plain JSON (safety.to_model_safe) before the model sees it.
  * Read tools only read. Write requests go through propose_* -> actions.py -> user confirmation.

Add a tool by writing a handler and one `_register(...)` call at the bottom.
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable
from itertools import islice

from django.utils import timezone

from services.budget import (
    get_budget_expenses,
    get_current_budget,
    get_remaining_budget,
    get_total_spent,
)
from services.foods import search_foods as search_food_library
from services.meals import (
    get_meal_ingredients,
    get_user_available_meal,
    get_user_available_meals,
    get_user_schedule,
    search_user_available_meals,
)
from services.pantry import (
    get_expired_items,
    get_expiring_items,
    get_running_low_items,
    get_user_pantry,
)
from services.shopping import get_user_shopping_lists
from services.timetable import MEAL_TYPES

from . import actions
from .safety import CATEGORY_LABELS, to_model_safe

logger = logging.getLogger(__name__)

MAX_ROWS = 40
PURCHASED_FIELDS = ("is_purchased", "purchased", "is_checked", "checked")


class ToolError(Exception):
    """A problem with the tool call itself. The text is written for the model."""


# =========================================================
# TOOL REGISTRY
# =========================================================

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    categories: tuple            # data categories touched; see safety.AIPermissions
    parameters: dict             # JSON-schema style, as Gemini expects
    handler: Callable            # (user, args) -> JSON-able data


TOOLS = {}


def _register(name, description, categories, parameters, handler):
    TOOLS[name] = Tool(name, description, tuple(categories), parameters, handler)


def get_tool_declarations(permissions):
    """Function declarations for the tools this user has allowed. Hidden tools can't be called."""
    declarations = []
    for tool in TOOLS.values():
        if not permissions.allows_all(tool.categories):
            continue
        declaration = {"name": tool.name, "description": tool.description}
        if tool.parameters.get("properties"):
            declaration["parameters"] = tool.parameters
        declarations.append(declaration)
    return declarations


def dispatch(user, name, args, permissions):
    """
    Run one tool call for `user`. Never raises.

    Returns {"ok": True, "data": ...} or {"ok": False, "error": "..."}.
    """
    tool = TOOLS.get(name)
    if tool is None:
        return {"ok": False, "error": "Unknown tool. Only use the tools you were given."}

    if not permissions.allows_all(tool.categories):
        blocked = [CATEGORY_LABELS.get(c, c) for c in tool.categories if not permissions.allows(c)]
        return {"ok": False,
                "error": "The user has turned off access to " + ", ".join(blocked) +
                         ". Don't use or guess that information."}

    if not isinstance(args, dict):
        args = {}

    try:
        data = tool.handler(user, args)
    except (ToolError, actions.ActionError) as error:
        return {"ok": False, "error": str(error)}
    except Exception:
        logger.exception("AI tool %s failed", name)          # no arguments or data in the log
        return {"ok": False, "error": "That information couldn't be loaded right now."}

    return {"ok": True, "data": to_model_safe(data)}


# =========================================================
# ARGUMENT HELPERS
# =========================================================


def _int_arg(
    args, name, *, required=False, default=None,
    minimum=None, maximum=None
):
    value = args.get(name)

    if value is None or value == "":
        if required:
            raise ToolError(f"{name} is required.")
        return default

    if isinstance(value, bool):
        raise ToolError(f"{name} must be a whole number.")

    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError):
        raise ToolError(f"{name} must be a whole number.")

    if not number.is_finite() or number != number.to_integral_value():
        raise ToolError(f"{name} must be a whole number.")

    number = int(number)

    if minimum is not None and number < minimum:
        raise ToolError(f"{name} must be at least {minimum}.")

    if maximum is not None and number > maximum:
        raise ToolError(f"{name} must be at most {maximum}.")

    return number


def _str_arg(args, name, *, required=False, max_len=100):
    value = args.get(name)
    if value is None or str(value).strip() == "":
        if required:
            raise ToolError(f"{name} is required.")
        return ""
    return " ".join(str(value).split())[:max_len]


def _date_arg(args, name, default):
    value = args.get(name)
    if value is None or value == "":
        return default
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ToolError(f"{name} must look like 2026-10-14.")


def _flag(obj, names):
    for name in names:
        if hasattr(obj, name):
            return bool(getattr(obj, name))
    return False


def _with_food(queryset):
    return queryset.select_related("food") if hasattr(queryset, "select_related") else queryset


def _capped(rows, limit=MAX_ROWS):
    collected = list(islice(iter(rows), limit + 1))
    truncated = len(collected) > limit
    return collected[:limit], truncated

def _num(value):
    return Decimal(value or 0)


# =========================================================
# PANTRY
# =========================================================

def _pantry_item(item, today, low_ids=None):
    expires = getattr(item, "expires_at", None)
    row = {
        "food": item.food.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "expires_at": expires,
        "days_until_expiry": (expires - today).days if expires else None,
    }
    if low_ids is not None:
        row["running_low"] = item.id in low_ids
    return row


def _get_pantry_items(user, args):
    today = timezone.localdate()
    low_ids = {i.id for i in get_running_low_items(user)}
    rows, truncated = _capped(_pantry_item(i, today, low_ids) for i in _with_food(get_user_pantry(user)))
    return {"count": len(rows), "items": rows, "truncated": truncated}


def _get_expiring_pantry_items(user, args):
    days = _int_arg(args, "days", default=7, minimum=1, maximum=30)
    today = timezone.localdate()
    expiring, _t1 = _capped(_pantry_item(i, today) for i in _with_food(get_expiring_items(user, days=days)))
    expired, _t2 = _capped(_pantry_item(i, today) for i in _with_food(get_expired_items(user)))
    return {
        "within_days": days,
        "expiring_soon": expiring,
        "already_past_expiry_date": expired,
        "note": "An expiry date alone doesn't prove food is safe or unsafe; give general food-safety advice.",
    }


# =========================================================
# FOOD LIBRARY AND MEALS
# =========================================================

def _search_foods(user, args):
    query = _str_arg(args, "query", required=True, max_len=60)
    rows, truncated = _capped(
        ({"food_id": f.id, "name": f.name, "default_unit": getattr(f, "default_unit", None),
          "perishable": getattr(f, "is_perishable", None)} for f in search_food_library(query)),
        limit=15,
    )
    return {"query": query, "foods": rows, "truncated": truncated}


def _search_meals(user, args):
    query = _str_arg(args, "query", max_len=60)
    meals = (
        search_user_available_meals(user, query)
        if query
        else get_user_available_meals(user)
    )
    rows, truncated = _capped(
        ({"meal_id": m.id, "name": m.name,
          "prep_minutes": getattr(m, "prep_time", None), "cook_minutes": getattr(m, "cook_time", None)}
         for m in meals),
        limit=20,
    )
    return {"meals": rows, "truncated": truncated}


def _ingredient_rows(meal):
    return [{"food_id": i.food_id, "food": i.food.name, "quantity": i.quantity, "unit": i.unit}
            for i in _with_food(get_meal_ingredients(meal))]


def _get_meal_details(user, args):
    meal = get_user_available_meal(
        user,
        _int_arg(args, "meal_id", required=True, minimum=1),
    )
    if meal is None:
        raise ToolError("That meal was not found.")
    ingredients = _ingredient_rows(meal)
    return {
        "meal_id": meal.id,
        "name": meal.name,
        "description": getattr(meal, "description", ""),
        "instructions": to_model_safe(getattr(meal, "instructions", "") or "", max_string=900),
        "prep_minutes": getattr(meal, "prep_time", None),
        "cook_minutes": getattr(meal, "cook_time", None),
        "ingredients": ingredients,
        "has_ingredients": bool(ingredients),
    }


def _check_meal_against_pantry(user, args):
    meal = get_user_available_meal(
        user,
        _int_arg(args, "meal_id", required=True, minimum=1),
    )
    if meal is None:
        raise ToolError("That meal was not found.")
    servings = _int_arg(args, "servings", default=1, minimum=1, maximum=50)

    stock = {}
    for item in get_user_pantry(user):
        by_unit = stock.setdefault(item.food_id, {})
        by_unit[item.unit] = by_unit.get(item.unit, Decimal("0")) + _num(item.quantity)

    ingredients = list(_with_food(get_meal_ingredients(meal)))
    if not ingredients:
        return {"meal": meal.name, "state": "unknown",
                "note": "This meal has no ingredients recorded, so it can't be compared with the pantry."}

        
    missing, mismatched, available = [], [], 0

    for ing in ingredients:
        needed = _num(ing.quantity) * servings
        held = stock.get(ing.food_id, {})

        if ing.unit not in held:
            available_quantities = [
                {"quantity": quantity, "unit": unit}
                for unit, quantity in held.items()
                if quantity > 0
            ]

            if available_quantities:
                mismatched.append({
                    "food": ing.food.name,
                    "needed_quantity": needed,
                    "needed_unit": ing.unit,
                    "available_quantities": available_quantities,
                })
            missing.append({
                "food": ing.food.name,
                "still_needed": needed,
                "unit": ing.unit,
            })
            continue

        held_quantity = held[ing.unit]

        if held_quantity >= needed:
            available += 1
        else:
            missing.append({
                "food": ing.food.name,
                "still_needed": needed - held_quantity,
                "unit": ing.unit,
            })

    state = ("partial" if available else "missing") if missing else "ready"

    return {
        "meal": meal.name,
        "servings": servings,
        "state": state,
        "ingredients_available": available,
        "ingredients_total": len(ingredients),
        "missing": missing,
        "assumed_available_but_unit_differs": mismatched,
    }


def _get_meal_plan(user, args):
    today = timezone.localdate()
    start = _date_arg(args, "start_date", today)
    end = _date_arg(args, "end_date", start + timedelta(days=6))
    if end < start:
        raise ToolError("end_date can't be before start_date.")
    if (end - start).days > 30:
        raise ToolError("Ask for at most 31 days at a time.")

    schedules = get_user_schedule(user).filter(date__gte=start, date__lte=end).select_related("meal")
    rows, truncated = _capped(
        ({"date": s.date, "meal_type": s.meal_type, "meal": s.meal.name, "meal_id": s.meal_id,
          "servings": s.servings} for s in sorted(schedules, key=lambda s: (s.date, str(s.meal_type)))),
        limit=60,
    )
    return {"from": start, "to": end, "planned": rows, "truncated": truncated,
            "note": "Scheduled meals, not confirmed as eaten."}


# =========================================================
# SHOPPING AND BUDGET
# =========================================================

def _get_shopping_lists(user, args):
    lists = get_user_shopping_lists(user)
    if hasattr(lists, "prefetch_related"):
        lists = lists.prefetch_related("items__food")

    out = []
    for shopping_list in list(lists)[:8]:
        items = [{"food": i.food.name, "quantity": i.quantity, "unit": i.unit,
                  "purchased": _flag(i, PURCHASED_FIELDS)} for i in shopping_list.items.all()]
        rows, truncated = _capped(items)
        out.append({"list_id": shopping_list.id, "name": shopping_list.name, "items": rows,
                    "still_to_buy": sum(1 for i in items if not i["purchased"]), "truncated": truncated})
    return {"lists": out}


def _get_budget_summary(user, args):
    today = timezone.localdate()
    budget = get_current_budget(user, today)
    if not budget:
        return {"has_active_budget": False,
                "note": "No budget covers today. Don't assume a budget amount."}

    amount, spent, remaining = _num(budget.amount), _num(get_total_spent(budget)), _num(get_remaining_budget(budget))
    expenses = sorted(get_budget_expenses(budget), key=lambda e: (e.date, e.id), reverse=True)
    recent, _t = _capped(
        ({"date": e.date, "description": e.description, "amount": e.amount} for e in expenses), limit=8)

    return {
        "has_active_budget": True,
        "currency": "KES",
        "name": budget.name,
        "period_start": budget.start_date,
        "period_end": budget.end_date,
        "budget_amount": amount,
        "spent": spent,
        "remaining": remaining,
        "percent_used": round(float(spent / amount * 100), 1) if amount > 0 else None,
        "days_left": max((budget.end_date - today).days, 0),
        "recent_expenses": recent,
    }


# =========================================================
# PROPOSALS (they park a request; the user confirms in the app)
# =========================================================

def _pending_response(pending):
    return {
        "status": "waiting_for_user_confirmation",
        "pending_action": pending,
        "tell_the_user": "This is NOT saved yet. Tell them to check the summary and press Confirm in the app.",
    }


def _propose_add_to_shopping_list(user, args):
    return _pending_response(actions.propose_shopping_items(user, args.get("items"), args.get("list_name")))


def _propose_schedule_meal(user, args):
    return _pending_response(actions.propose_schedule_meal(
        user,
        args.get("meal_id"),
        args.get("date"),
        args.get("meal_type"),
        args.get("servings", 1),
    ))


# =========================================================
# REGISTRATION
# =========================================================

_NO_ARGS = {"type": "object", "properties": {}}

_register(
    "get_pantry_items",
    "List everything in the user's pantry with quantity, unit, expiry date and whether it is running low.",
    ("pantry",), _NO_ARGS, _get_pantry_items)

_register(
    "get_expiring_pantry_items",
    "List pantry items expiring within some days, plus items already past their recorded expiry date.",
    ("pantry",),
    {"type": "object", "properties": {
        "days": {"type": "integer", "description": "Look-ahead window in days (1-30). Default 7."}}},
    _get_expiring_pantry_items)

_register(
    "search_foods",
    "Search the FoodiePlug food library by name. Returns food_id values needed for shopping proposals.",
    ("foods",),
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "Food name or part of it, e.g. 'tomato'."}},
     "required": ["query"]},
    _search_foods)

_register(
    "search_meals",
    "Search the saved meal library by name, or list meals when no query is given.",
    ("meals",),
    {"type": "object", "properties": {
        "query": {"type": "string", "description": "Optional meal name or part of it."}}},
    _search_meals)

_register(
    "get_meal_details",
    "Get one saved meal: description, instructions, prep/cook time and its ingredients with quantities.",
    ("meals",),
    {"type": "object", "properties": {"meal_id": {"type": "integer"}}, "required": ["meal_id"]},
    _get_meal_details)

_register(
    "check_meal_against_pantry",
    "Compare a saved meal's ingredients with the user's pantry and say what is missing.",
    ("meals", "pantry"),
    {"type": "object", "properties": {
        "meal_id": {"type": "integer"},
        "servings": {"type": "integer", "description": "Number of servings (1-50). Default 1."}},
     "required": ["meal_id"]},
    _check_meal_against_pantry)

_register(
    "get_meal_plan",
    "Get the user's scheduled meals between two dates (default: the next 7 days; at most 31 days).",
    ("meals",),
    {"type": "object", "properties": {
        "start_date": {"type": "string", "description": "YYYY-MM-DD. Default today."},
        "end_date": {"type": "string", "description": "YYYY-MM-DD. Default 6 days after start_date."}}},
    _get_meal_plan)

_register(
    "get_shopping_lists",
    "Get the user's shopping lists with their items and what is still to buy.",
    ("shopping",), _NO_ARGS, _get_shopping_lists)

_register(
    "get_budget_summary",
    "Get the user's current food budget: amount, spent, remaining, days left and recent expenses (KES).",
    ("budget",), _NO_ARGS, _get_budget_summary)

_register(
    "propose_add_to_shopping_list",
    "PROPOSE adding foods to a shopping list. Nothing is saved until the user confirms in the app. "
    "Find food_id values with search_foods first.",
    ("shopping", "foods"),
    {"type": "object", "properties": {
        "items": {"type": "array", "description": "Foods to add (max 25).", "items": {
            "type": "object", "properties": {
                "food_id": {"type": "integer"},
                "quantity": {"type": "number"},
                "unit": {"type": "string", "enum": list(actions.ALLOWED_UNITS)}},
            "required": ["food_id", "quantity", "unit"]}},
        "list_name": {"type": "string", "description": "Existing list name, or a new one. Optional."}},
     "required": ["items"]},
    _propose_add_to_shopping_list)

_register(
    "propose_schedule_meal",
    "PROPOSE putting a saved meal on the planner. Nothing is saved until the user confirms in the app.",
    ("meals",),
    {"type": "object", "properties": {
        "meal_id": {"type": "integer"},
        "date": {"type": "string", "description": "YYYY-MM-DD, today or later."},
        "meal_type": {"type": "string", "enum": list(MEAL_TYPES)},
        "servings": {"type": "integer", "description": "1-50. Default 1."}},
     "required": ["meal_id", "date", "meal_type"]},
    _propose_schedule_meal)
