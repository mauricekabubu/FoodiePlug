"""
apps/insights — analytics for the Insights page (no templates, no HTTP).

Everything here is calculated from records that already exist in FoodiePlug:
  budgets + their expenses, shopping lists + items, pantry items, meal schedules.
Each collector is isolated: if one module fails, that section is marked unavailable and the
rest of the page still renders. Nothing is invented: when a number can't be calculated
honestly, it is left out or the section says what data is missing.

Public entry point:  build_insights_page(user, today, period_key, custom_start, custom_end, links)
  `links(name, *args)` must return a URL or None (None => that action is simply not shown).
"""

import logging
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal

from services.budget import (
    get_user_budgets,
    get_current_budget,
    get_total_spent,
    get_budget_expenses,
)
from services.pantry import (
    get_user_pantry,
    get_expiring_items,
    get_expired_items,
    get_running_low_items,
)
from services.meals import get_user_schedule, get_all_meals, get_meal_ingredients
from services.shopping import get_user_shopping_lists

logger = logging.getLogger(__name__)

ZERO = Decimal("0")
EXPIRING_DAYS = 7
SOON_DAYS = 3
UPCOMING_DAYS = 7
MAX_CUSTOM_DAYS = 366
MIN_DAYS_FOR_PROJECTION = 7
MAX_INSIGHTS = 10

PERIOD_OPTIONS = [
    ("this_week", "This week"),
    ("this_month", "This month"),
    ("last_month", "Last month"),
    ("last_30", "Last 30 days"),
    ("last_90", "Last 90 days"),
    ("custom", "Custom range"),
]


# =========================================================
# REPORTING PERIOD
# =========================================================

def _month_start(day):
    return day.replace(day=1)


def _month_end(day):
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def resolve_period(key, today, custom_start=None, custom_end=None):
    """Return the selected period and the equivalent previous one. Dates are inclusive."""
    labels = dict(PERIOD_OPTIONS)
    error = None

    if key not in labels:
        key = "this_month"

    if key == "this_week":
        start = today - timedelta(days=today.weekday())
        end = today
        prev_start = start - timedelta(days=7)
        prev_end = prev_start + (end - start)

    elif key == "this_month":
        start, end = _month_start(today), today
        prev_start = _month_start(start - timedelta(days=1))
        prev_end = min(prev_start + (end - start), _month_end(prev_start))

    elif key == "last_month":
        end = _month_start(today) - timedelta(days=1)
        start = _month_start(end)
        prev_end = start - timedelta(days=1)
        prev_start = _month_start(prev_end)

    elif key == "last_30":
        start, end = today - timedelta(days=29), today
        prev_end, prev_start = start - timedelta(days=1), start - timedelta(days=30)

    elif key == "last_90":
        start, end = today - timedelta(days=89), today
        prev_end, prev_start = start - timedelta(days=1), start - timedelta(days=90)

    else:  # custom
        try:
            start = date.fromisoformat(custom_start or "")
            end = date.fromisoformat(custom_end or "")
            if end < start:
                raise ValueError
            if (end - start).days + 1 > MAX_CUSTOM_DAYS:
                error = f"Custom ranges can cover up to {MAX_CUSTOM_DAYS} days. Showing the most recent {MAX_CUSTOM_DAYS}."
                start = end - timedelta(days=MAX_CUSTOM_DAYS - 1)
        except ValueError:
            error = "Enter a valid start and end date. Showing this month instead."
            key, start, end = "this_month", _month_start(today), today
            prev_start = _month_start(start - timedelta(days=1))
            prev_end = min(prev_start + (end - start), _month_end(prev_start))
        else:
            span = (end - start).days + 1
            prev_end, prev_start = start - timedelta(days=1), start - timedelta(days=span)

    return {
        "key": key, "label": labels[key], "start": start, "end": end,
        "days": (end - start).days + 1,
        "prev_start": prev_start, "prev_end": prev_end,
        "custom_start": start.isoformat() if key == "custom" else "",
        "custom_end": end.isoformat() if key == "custom" else "",
        "error": error,
    }


# =========================================================
# SMALL HELPERS
# =========================================================

def _safe(name, func, *args):
    """Run one collector; a failure marks only that section unavailable."""
    try:
        return func(*args)
    except Exception:
        logger.exception("Insights: %s could not be calculated", name)
        return None


def _kes(value):
    return f"KES {Decimal(value):,.0f}"


def _compare(current, previous):
    """Previous-period comparison, only when the previous period has a real figure."""
    if previous is None or previous <= 0:
        return None
    pct = (Decimal(current) - Decimal(previous)) / Decimal(previous) * 100
    if abs(pct) < 1:
        return {"direction": "flat", "text": "About the same as the previous period"}
    direction = "up" if pct > 0 else "down"
    return {"direction": direction,
            "text": f"{abs(pct):.0f}% {'higher' if pct > 0 else 'lower'} than the previous period"}


def _link(links, label, name, *args):
    url = links(name, *args)
    return {"label": label, "url": url} if url else None


def _insight(id, category, title, detail, kind, priority, evidence=None, action=None, ask=None):
    return {
        "id": id, "category": category,
        "category_label": {"budget": "Budget", "shopping": "Shopping", "pantry": "Pantry", "meals": "Meals"}[category],
        "title": title, "detail": detail, "evidence": evidence or [],
        "kind": kind, "kind_label": {"measured": "Measured", "estimate": "Estimate", "suggestion": "Suggestion"}[kind],
        "priority": priority, "action": action, "ask": ask,
    }


# =========================================================
# SPENDING
# =========================================================

def _load_budgets_and_expenses(user):
    budgets = list(get_user_budgets(user))
    expenses = []
    for budget in budgets:
        for e in get_budget_expenses(budget):
            expenses.append({"date": e.date, "amount": Decimal(e.amount), "description": e.description or "",
                             "budget_id": budget.id, "id": e.id})
    return budgets, expenses


def _in_range(expenses, start, end):
    return [e for e in expenses if start <= e["date"] <= end]


def _covered(budgets, start, end):
    """Is any budget active during [start, end]? Only then can we say 'nothing spent' honestly."""
    return any(b.start_date <= end and b.end_date >= start for b in budgets)


def _granularity(days):
    return "day" if days <= 14 else "week" if days <= 120 else "month"


def _buckets(start, end, granularity):
    out, cursor = [], start
    while cursor <= end:
        if granularity == "day":
            b_end, label = cursor, cursor.strftime("%d %b")
        elif granularity == "week":
            b_end, label = min(cursor + timedelta(days=6), end), cursor.strftime("%d %b")
        else:
            b_end, label = min(_month_end(cursor), end), cursor.strftime("%b %Y")
        out.append((cursor, b_end, label))
        cursor = b_end + timedelta(days=1)
    return out


def spending_section(budgets, expenses, period, links):
    in_period = _in_range(expenses, period["start"], period["end"])
    in_prev = _in_range(expenses, period["prev_start"], period["prev_end"])
    total = sum((e["amount"] for e in in_period), ZERO)
    prev_total = sum((e["amount"] for e in in_prev), ZERO) if in_prev else None

    granularity = _granularity(period["days"])
    series = []
    for b_start, b_end, label in _buckets(period["start"], period["end"], granularity):
        amount = sum((e["amount"] for e in in_period if b_start <= e["date"] <= b_end), ZERO)
        series.append({"label": label, "start": b_start.isoformat(), "end": b_end.isoformat(),
                       "amount": float(amount), "tracked": _covered(budgets, b_start, b_end)})

    descriptions = defaultdict(lambda: {"count": 0, "total": ZERO, "label": ""})
    for e in in_period:
        key = e["description"].strip().lower()
        if key:
            d = descriptions[key]
            d["count"] += 1
            d["total"] += e["amount"]
            d["label"] = d["label"] or e["description"].strip()

    repeated = sorted(({"name": d["label"], "count": d["count"], "total": d["total"]}
                       for d in descriptions.values() if d["count"] >= 2),
                      key=lambda r: (-r["count"], -r["total"]))[:5]

    largest = sorted(in_period, key=lambda e: -e["amount"])[:5]

    return {
        "total": total,
        "prev_total": prev_total,
        "compare": _compare(total, prev_total),
        "count": len(in_period),
        "has_expenses": bool(in_period),
        "tracked": _covered(budgets, period["start"], period["end"]),
        "granularity": granularity,
        "granularity_label": {"day": "day", "week": "week", "month": "month"}[granularity],
        "series": series,
        "has_untracked_buckets": any(not s["tracked"] for s in series),
        "largest": [{"description": e["description"], "amount": e["amount"], "date": e["date"],
                     "url": links("budgets:detail", e["budget_id"])} for e in largest],
        "repeated": repeated,
        # Expenses carry no category today, so a category breakdown can't be calculated.
        "categories": None,
    }


def budget_section(user, budgets, period, today, links):
    reference = min(period["end"], today)
    current = _safe("current budget", get_current_budget, user, reference)

    rows = []
    overlapping = [b for b in budgets if b.start_date <= period["end"] and b.end_date >= period["start"]]
    for b in sorted(overlapping, key=lambda b: b.start_date, reverse=True)[:4]:
        spent = Decimal(get_total_spent(b) or 0)
        amount = Decimal(b.amount)
        total_days = (b.end_date - b.start_date).days + 1
        elapsed = min(max((today - b.start_date).days + 1, 0), total_days)
        projected = None
        if b.end_date >= today and elapsed >= MIN_DAYS_FOR_PROJECTION and spent > 0:
            projected = (spent / elapsed * total_days).quantize(Decimal("1"))
        scale = max(amount, spent, projected or ZERO) or Decimal("1")
        rows.append({
            "id": b.id, "name": b.name, "amount": amount, "spent": spent,
            "usage": (spent / amount * 100).quantize(Decimal("0.1")) if amount > 0 else ZERO,
            "projected": projected,
            "start": b.start_date, "end": b.end_date,
            "allocated_pct": float(amount / scale * 100),
            "actual_pct": float(spent / scale * 100),
            "projected_pct": float(projected / scale * 100) if projected else None,
            "url": links("budgets:detail", b.id),
            "is_current": bool(current and current.id == b.id),
        })

    active = next((r for r in rows if r["is_current"]), None)
    return {"rows": rows, "active": active}


# =========================================================
# SHOPPING
# =========================================================

def shopping_section(user, links):
    lists = list(get_user_shopping_lists(user))
    items_by_list = {l.id: list(l.items.all()) for l in lists}      # assumes related_name="items"

    all_items = [i for items in items_by_list.values() for i in items]
    purchased = [i for i in all_items if getattr(i, "is_purchased", False)]
    completed = [l for l in lists if items_by_list[l.id] and all(getattr(i, "is_purchased", False) for i in items_by_list[l.id])]

    frequent = Counter(i.food.name for i in purchased).most_common(5)
    return {
        "lists": lists, "items_by_list": items_by_list,
        "list_count": len(lists),
        "item_count": len(all_items),
        "purchased_count": len(purchased),
        "completed_lists": len(completed),
        "frequent_foods": [{"name": n, "count": c} for n, c in frequent],
        "url": links("shopping_lists"),
        "has_data": bool(lists),
    }


# =========================================================
# PANTRY
# =========================================================

def pantry_section(user, today, links):
    items = list(get_user_pantry(user))
    expiring = list(get_expiring_items(user, days=EXPIRING_DAYS))
    expired = list(get_expired_items(user))
    low = list(get_running_low_items(user))

    def view(item):
        return {"name": item.food.name, "expires_at": getattr(item, "expires_at", None),
                "days_left": (item.expires_at - today).days if getattr(item, "expires_at", None) else None,
                "quantity": item.quantity, "unit": item.unit, "food_id": item.food_id}

    return {
        "item_count": len(items), "has_data": bool(items),
        "expiring": [view(i) for i in expiring], "expired": [view(i) for i in expired],
        "low": [view(i) for i in low],
        "risk_count": len(expiring) + len(expired),
        "stock": _stock(items),
        "url": links("pantry:pantry"),
    }


def _stock(items):
    stock = defaultdict(lambda: defaultdict(lambda: ZERO))
    for item in items:
        stock[item.food_id][item.unit] += Decimal(item.quantity or 0)
    return stock


# =========================================================
# MEALS
# =========================================================

def meals_section(user, period, today, pantry, links):
    schedules = get_user_schedule(user)
    in_period = list(schedules.filter(date__gte=period["start"], date__lte=period["end"]))
    upcoming_end = today + timedelta(days=UPCOMING_DAYS - 1)
    upcoming = list(schedules.filter(date__gte=today, date__lte=upcoming_end))
    saved = len(list(get_all_meals()))
    has_any = bool(schedules.exists())

    by_type = Counter(s.meal_type for s in in_period)
    top = Counter((s.meal_id, s.meal.name) for s in in_period).most_common(5)
    total = len(in_period)
    distribution = [{"type": t.replace("_", " ").title(), "count": c, "pct": round(c / total * 100)}
                    for t, c in sorted(by_type.items(), key=lambda kv: -kv[1])] if total else []

    # ingredient check for upcoming meals (pantry comparison, same-unit quantities only)
    upcoming_detail, ingredients_cache = [], {}
    expiring_ids = {p["food_id"]: p for p in (pantry["expiring"] + pantry["expired"])} if pantry else {}
    stock = pantry["stock"] if pantry else {}

    for s in upcoming:
        if s.meal_id not in ingredients_cache:
            ingredients_cache[s.meal_id] = list(get_meal_ingredients(s.meal))
        ingredients = ingredients_cache[s.meal_id]
        missing, uses_expiring = [], []
        for ing in ingredients:
            needed = Decimal(ing.quantity or 0) * Decimal(s.servings or 1)
            held = stock.get(ing.food_id, {}) if pantry else {}
            if ing.unit in held:
                ok = held[ing.unit] >= needed
            else:
                ok = any(q > 0 for q in held.values())
            if not ok:
                missing.append(ing.food.name)
            if ing.food_id in expiring_ids and ok:
                uses_expiring.append(ing.food.name)
        upcoming_detail.append({"meal": s.meal.name, "date": s.date, "meal_type": s.meal_type,
                                "has_ingredients": bool(ingredients), "missing": missing, "uses_expiring": uses_expiring})

    return {
        "planned": total, "has_any": has_any, "saved": saved,
        "distribution": distribution,
        "top": [{"name": name, "count": c} for (_id, name), c in top],
        "variety": len({s.meal_id for s in in_period}),
        "upcoming": upcoming_detail,
        "url": links("meals:timetable"), "library_url": links("meals:meal_library"),
    }


# =========================================================
# KEY INSIGHTS (each one carries its own evidence)
# =========================================================

def build_feed(spending, budgets_s, shopping, pantry, meals, period, today, links, ask_url):
    feed = []

    def ask(prompt):
        return f"{ask_url}?q={prompt.replace(' ', '+')}" if ask_url else None

    budget_url = (budgets_s["active"] or {}).get("url") if budgets_s else None
    budget_action = {"label": "Review budget", "url": budget_url} if budget_url else _link(links, "Open budgets", "budgets:dashboard")

    # ---- budget ----
    if spending:
        c = spending["compare"]
        if c and c["direction"] == "up" and spending["total"] - spending["prev_total"] >= 200 \
                and spending["total"] > spending["prev_total"] * Decimal("1.15"):
            feed.append(_insight(
                "spending_up", "budget", "Your food spending is higher than before",
                "Recorded spending this period is noticeably above the previous equivalent period.",
                "measured", 75,
                [f"This period: {_kes(spending['total'])}", f"Previous period: {_kes(spending['prev_total'])}", c["text"]],
                budget_action, ask("Why has my food spending increased?")))

        if spending["count"] >= 3 and spending["largest"]:
            top = spending["largest"][0]
            share = top["amount"] / spending["total"] * 100 if spending["total"] else ZERO
            if share >= 35:
                feed.append(_insight(
                    "big_purchase", "budget", f"One purchase made up {share:.0f}% of your spending",
                    f"“{top['description']}” was your largest recorded expense this period.",
                    "measured", 55, [f"{_kes(top['amount'])} of {_kes(spending['total'])}"],
                    budget_action, ask("Which of my food expenses was the biggest?")))

        for r in spending["repeated"][:2]:
            if r["count"] >= 3:
                feed.append(_insight(
                    f"repeat_{r['name'].lower()}", "budget", f"You've recorded “{r['name']}” {r['count']} times",
                    "A repeated purchase can be worth a look: you may prefer buying it less often or in a different amount.",
                    "suggestion", 40, [f"{r['count']} expenses totalling {_kes(r['total'])}"],
                    budget_action, ask("What patterns can you identify in my shopping?")))

    if budgets_s and budgets_s["active"]:
        a = budgets_s["active"]
        if a["usage"] >= 85:
            feed.append(_insight(
                "budget_limit", "budget",
                "You've passed your budget" if a["usage"] >= 100 else "You're close to your budget limit",
                f"“{a['name']}” has {'no money left' if a['usage'] >= 100 else 'little left'} for the rest of its period.",
                "measured", 95, [f"Spent {_kes(a['spent'])} of {_kes(a['amount'])} ({a['usage']:.0f}%)"],
                {"label": "Review budget", "url": a["url"]} if a["url"] else None,
                ask("How can I make my food budget last longer?")))
        elif a["projected"] and a["projected"] > a["amount"]:
            feed.append(_insight(
                "budget_pace", "budget", "At this pace you may go over budget",
                "This is a straight-line estimate from your recorded spending so far, not a certainty.",
                "estimate", 70, [f"Estimated total: {_kes(a['projected'])}", f"Budget: {_kes(a['amount'])}"],
                {"label": "Review budget", "url": a["url"]} if a["url"] else None,
                ask("How can I stay within my remaining budget?")))

    # ---- pantry ----
    if pantry:
        if pantry["expired"]:
            names = ", ".join(i["name"] for i in pantry["expired"][:4])
            feed.append(_insight(
                "pantry_expired", "pantry", f"{len(pantry['expired'])} pantry item{'s' if len(pantry['expired']) != 1 else ''} past the recorded expiry date",
                "Check these and update your pantry. This isn't counted as food waste unless you record it.",
                "measured", 80, [names], _link(links, "Check pantry", "pantry:pantry"), ask("What should I use before it expires?")))

        soon = [i for i in pantry["expiring"] if i["days_left"] is not None and 0 <= i["days_left"] <= SOON_DAYS]
        if soon:
            feed.append(_insight(
                "pantry_soon", "pantry", f"{len(soon)} item{'s' if len(soon) != 1 else ''} to use within {SOON_DAYS} days",
                "These are approaching the expiry date you recorded.",
                "measured", 85, [f"{i['name']} — {'today' if i['days_left'] == 0 else f'in {i['days_left']} day' + ('s' if i['days_left'] != 1 else '')}" for i in soon[:4]],
                _link(links, "Check pantry", "pantry:pantry"), ask("What should I use before it expires?")))

        if pantry["low"]:
            feed.append(_insight(
                "pantry_low", "pantry", f"{len(pantry['low'])} item{'s' if len(pantry['low']) != 1 else ''} running low",
                "These have dropped below the minimum quantity you set.",
                "measured", 45, [", ".join(i["name"] for i in pantry["low"][:5])],
                _link(links, "Check pantry", "pantry:pantry")))

    # ---- shopping ----
    if shopping and shopping["has_data"]:
        stock = pantry["stock"] if pantry else {}
        for l in shopping["lists"]:
            open_items = [i for i in shopping["items_by_list"][l.id] if not getattr(i, "is_purchased", False)]
            counts = Counter(i.food_id for i in open_items)
            dupes = [i.food.name for i in open_items if counts[i.food_id] > 1]
            if dupes:
                names = sorted(set(dupes))
                feed.append(_insight(
                    f"dupes_{l.id}", "shopping", f"“{l.name}” lists the same food more than once",
                    "You may want to combine these entries.", "measured", 60, [", ".join(names[:4])],
                    _link(links, "View shopping list", "shopping_list_detail", l.id)))

            already = []
            for i in open_items:
                held = stock.get(i.food_id, {}) if pantry else {}
                if i.unit in held and held[i.unit] >= Decimal(i.quantity or 0) > 0:
                    already.append(f"{i.food.name}: need {Decimal(i.quantity):g} {i.unit}, pantry has {held[i.unit]:g} {i.unit}")
            if already:
                feed.append(_insight(
                    f"have_{l.id}", "shopping", f"You may already have {len(already)} item{'s' if len(already) != 1 else ''} from “{l.name}”",
                    "Your pantry holds at least the quantity on the list, so you may not need to buy these.",
                    "suggestion", 65, already[:3], _link(links, "View shopping list", "shopping_list_detail", l.id),
                    ask("What should I remove from my shopping list?")))

    # ---- meals ----
    if meals:
        with_data = [m for m in meals["upcoming"] if m["has_ingredients"]]
        short = [m for m in with_data if m["missing"]]
        if short:
            feed.append(_insight(
                "meals_missing", "meals", f"{len(short)} of your next {len(with_data)} planned meals need ingredients you don't have",
                "Compared with what's recorded in your pantry.", "measured", 70,
                [f"{m['meal']} ({m['date']:%a}): {', '.join(m['missing'][:3])}" for m in short[:3]],
                _link(links, "Open meal planner", "meals:timetable"), ask("Which of my planned meals need shopping?")))

        for m in meals["upcoming"]:
            if m["uses_expiring"]:
                feed.append(_insight(
                    f"use_expiring_{m['meal']}_{m['date']}", "meals", f"{m['meal']} uses food that's close to expiring",
                    "Your plan already includes this, so cook it before the ingredient runs out of time.",
                    "suggestion", 78, [f"{', '.join(m['uses_expiring'][:3])} — planned {m['date']:%A}"],
                    _link(links, "Open meal planner", "meals:timetable")))
                break

        for t in meals["top"]:
            if t["count"] >= 3:
                feed.append(_insight(
                    f"repeat_meal_{t['name']}", "meals", f"{t['name']} is planned {t['count']} times",
                    "A lot of repetition isn't wrong, but mixing in another meal may add variety.",
                    "measured", 35, [f"{t['count']} scheduled meals in this period"],
                    _link(links, "Open meal planner", "meals:timetable")))
                break

        if meals["saved"] and not meals["upcoming"]:
            feed.append(_insight(
                "nothing_planned", "meals", f"Nothing is planned for the next {UPCOMING_DAYS} days",
                "You have saved meals ready to schedule.", "suggestion", 50,
                [f"{meals['saved']} saved meal{'s' if meals['saved'] != 1 else ''}"],
                _link(links, "Plan a meal", "meals:timetable")))

    unique = {}
    for item in feed:
        unique.setdefault(item["id"], item)
    return sorted(unique.values(), key=lambda i: -i["priority"])[:MAX_INSIGHTS]


# =========================================================
# PAGE
# =========================================================

def build_insights_page(user, today, period_key, custom_start, custom_end, links):
    period = resolve_period(period_key, today, custom_start, custom_end)
    ask_url = links("ai:page")

    loaded = _safe("budgets and expenses", _load_budgets_and_expenses, user)
    budgets, expenses = loaded if loaded else ([], [])
    spending = _safe("spending", spending_section, budgets, expenses, period, links) if loaded else None
    budgets_s = _safe("budgets", budget_section, user, budgets, period, today, links) if loaded else None
    shopping = _safe("shopping", shopping_section, user, links)
    pantry = _safe("pantry", pantry_section, user, today, links)
    meals = _safe("meals", meals_section, user, period, today, pantry, links)
    feed = _safe("key insights", build_feed, spending, budgets_s, shopping, pantry, meals, period, today, links, ask_url) or []

    overview = _overview(spending, budgets_s, shopping, pantry, meals, period, links)

    return {
        "period": period, "periods": PERIOD_OPTIONS, "ask_url": ask_url,
        "overview": overview, "insights": feed,
        "spending": spending, "budgets": budgets_s, "shopping": shopping, "pantry": pantry, "meals": meals,
        "unavailable": [n for n, v in (("spending", spending), ("shopping", shopping), ("pantry", pantry), ("meals", meals)) if v is None],
    }


def _overview(spending, budgets_s, shopping, pantry, meals, period, links):
    cards = []

    # 1. Food spending (actual, recorded expenses)
    if spending and (spending["has_expenses"] or spending["tracked"]):
        cards.append({"key": "spending", "title": "Food spending", "value": _kes(spending["total"]),
                      "caption": f"Recorded expenses, {period['start']:%d %b} – {period['end']:%d %b}.",
                      "compare": spending["compare"],
                      "note": None if spending["has_expenses"] else "A budget was active, but no expenses were recorded.",
                      "link": _link(links, "Open Budget", "budgets:dashboard")})
    else:
        cards.append({"key": "spending", "title": "Food spending", "value": None,
                      "empty": "No expenses recorded for this period, and no budget was active. Spending can't be shown until you track it.",
                      "link": _link(links, "Set up a budget", "budgets:dashboard")})

    # 2. Budget usage
    active = budgets_s["active"] if budgets_s else None
    if active:
        cards.append({"key": "budget", "title": "Budget usage", "value": f"{active['usage']:.0f}%",
                      "caption": f"{_kes(active['spent'])} of {_kes(active['amount'])} used in “{active['name']}”.",
                      "compare": None,
                      "note": f"Estimated total at this pace: {_kes(active['projected'])}" if active["projected"] else None,
                      "link": {"label": "Open budget", "url": active["url"]} if active["url"] else None})
    else:
        cards.append({"key": "budget", "title": "Budget usage", "value": None,
                      "empty": "No budget is active in this period.",
                      "link": _link(links, "Set a budget", "budgets:dashboard")})

    # 3. Shopping (current snapshot: items have no purchase date to filter by period)
    if shopping and shopping["has_data"]:
        cards.append({"key": "shopping", "title": "Shopping right now", "value": f"{shopping['purchased_count']} of {shopping['item_count']}",
                      "caption": f"items purchased across {shopping['list_count']} list{'s' if shopping['list_count'] != 1 else ''}. A snapshot, not limited to the period.",
                      "compare": None, "note": None, "link": _link(links, "Open Shopping", "shopping_lists")})
    else:
        cards.append({"key": "shopping", "title": "Shopping right now", "value": None,
                      "empty": "No shopping lists yet.", "link": _link(links, "Start a list", "shopping_lists")})

    # 4. Meals planned
    if meals and (meals["has_any"] or meals["planned"]):
        cards.append({"key": "meals", "title": "Meals planned", "value": str(meals["planned"]),
                      "caption": "Meals scheduled in this period. Scheduled, not confirmed as eaten.",
                      "compare": None, "note": None, "link": _link(links, "Open Meal Planner", "meals:timetable")})
    else:
        cards.append({"key": "meals", "title": "Meals planned", "value": None,
                      "empty": "Nothing has been scheduled yet.", "link": _link(links, "Plan a meal", "meals:timetable")})

    # 5. Pantry expiry risks
    if pantry and pantry["has_data"]:
        cards.append({"key": "pantry", "title": "Pantry expiry risks", "value": str(pantry["risk_count"]),
                      "caption": f"items expired or expiring within {EXPIRING_DAYS} days, as of today.",
                      "compare": None, "note": None, "link": _link(links, "Check Pantry", "pantry:pantry")})
    else:
        cards.append({"key": "pantry", "title": "Pantry expiry risks", "value": None,
                      "empty": "Your pantry is empty, so there's nothing to check.", "link": _link(links, "Add pantry items", "pantry:pantry")})

    return cards