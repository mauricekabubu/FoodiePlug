from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib.auth.models import User
from django.contrib import messages
from dotenv import load_dotenv
import logging

from .models import Profile, Message

load_dotenv()  # Load environment variables

logger = logging.getLogger(__name__)


User = get_user_model()



"""
Dashboard view: replaces the existing `dashboard` view (URL name "dashboard").

Every figure comes from the user's own data in the meals, budget, shopping and
pantry services. Nothing is estimated or invented: where the project has no data
for something (meal prices, planned spend) the dashboard simply doesn't show it.

Each data source is loaded inside _safe(), so a problem in one module (for
example the shopping list) logs an error and leaves that card empty instead of
taking the whole dashboard down.
"""

import logging
from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse

# Reused so the dashboard and the planner always agree on "available / missing".
# Tip: move these three into a shared service (e.g. services/meal_planning.py).
from apps.meals.views import (
    SHOPPING_LIST_NAME,
    _fmt_qty,
    _meal_availability,
    _pantry_stock,
)

import os

FOODIEPLUG_CREDENTIALS_ENCRYPTION_KEY = os.environ.get(
    "FOODIEPLUG_CREDENTIALS_ENCRYPTION_KEY",
    "",
)

from services.budget import (
    get_budget_expenses,
    get_current_budget,
    get_remaining_budget,
    get_total_spent,
)
from services.meals import get_user_schedule
from services.pantry import (
    get_expired_items,
    get_expiring_items,
    get_running_low_items,
    get_user_pantry,
)
from services.shopping import get_user_shopping_lists
from services.timetable import MEAL_TYPES, get_week_end, get_week_start


from apps.ai.services.user_config import (
    GEMINI_MODELS,
    get_user_ai_config,
    save_user_api_key,
    remove_user_api_key,
    test_user_api_key,
)
from apps.ai.services.credentials import CredentialEncryptionError

import logging

from django.utils import timezone

from apps.ai.services.credentials import (
    encrypt_api_key,
    decrypt_api_key,
)



logger = logging.getLogger(__name__)

BUDGET_WARNING_PERCENT = Decimal("85")
PANTRY_PREVIEW = 6
SHOPPING_PREVIEW = 6
ACTIVITY_LIMIT = 5
INSIGHT_LIMIT = 6

# Field names are tried in order; the first one the model has is used.
PURCHASED_FIELDS = ("is_purchased", "purchased", "is_checked", "checked")
DONE_FIELDS = ("is_done", "is_completed", "completed")

EMPTY_PANTRY = {"items": [], "display": [], "total": 0,
                "low_count": 0, "expiring_count": 0, "expired_count": 0}
EMPTY_SHOPPING = {"list": None, "rows": [], "count": 0, "pending": 0}
EMPTY_PLAN = {"today_meals": [], "week_days": [], "planned": 0, "ready": 0,
              "with_data": 0, "no_ingredients": 0, "empty_slots": 0}


# =========================================================
# SMALL HELPERS
# =========================================================

def _safe(loader, fallback, *args):
    try:
        return loader(*args)
    except Exception:
        logger.exception("Dashboard: %s failed", loader.__name__)
        return fallback


def _kes(value):
    return f"KES {Decimal(value):,.0f}"


def _s(count):
    return "" if count == 1 else "s"


def _have(count):
    return "has" if count == 1 else "have"


def _time_of_day(hour):
    if hour < 12:
        return "morning"
    if hour < 17:
        return "afternoon"
    return "evening"


def _relative_day(day, today):
    delta = (today - day).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if 1 < delta < 7:
        return f"{delta} days ago"
    return f"{day:%d %b}"


def _flag(obj, names):
    """First matching boolean attribute on obj, else False."""
    for name in names:
        if hasattr(obj, name):
            return bool(getattr(obj, name))
    return False


def _slot_order(meal_type):
    try:
        return list(MEAL_TYPES).index(meal_type)
    except ValueError:
        return len(MEAL_TYPES)


def _meal_image_url(meal):
    image = getattr(meal, "image", None)
    try:
        if image:
            return image.url
    except ValueError:
        pass
    return getattr(meal, "image_url", "") or ""


def _minutes_label(meal):
    total = (getattr(meal, "prep_time", None) or 0) + (getattr(meal, "cook_time", None) or 0)
    return f"{total} min" if total else ""


def _pantry_label(info):
    if info["state"] == "ready":
        return "Ready from pantry"
    if info["state"] == "unknown":
        return "No ingredients added yet"
    return f"{info['available']} of {info['total']} ingredients in pantry"


# =========================================================
# DATA LOADERS
# =========================================================

def _load_budget(user, today):
    """(summary dict or None, expenses newest first)."""
    budget = get_current_budget(user, today)
    if not budget:
        return None, []

    amount = Decimal(budget.amount)
    spent = Decimal(get_total_spent(budget) or 0)
    remaining = Decimal(get_remaining_budget(budget) or 0)
    percent = spent / amount * 100 if amount > 0 else Decimal("0")

    expenses = sorted(get_budget_expenses(budget), key=lambda e: (e.date, e.id), reverse=True)

    summary = {
        "id": budget.id,
        "name": budget.name,
        "amount": amount,
        "spent": spent,
        "remaining": remaining,
        "percent_spent": int(min(percent, Decimal("100"))),
        "percent_used": percent,
        "days_remaining": max((budget.end_date - today).days, 0),
        "period": f"{budget.start_date:%d %b} – {budget.end_date:%d %b}",
        "is_over": percent >= 100,
        "is_warning": BUDGET_WARNING_PERCENT <= percent < 100,
    }
    return summary, expenses


def _load_pantry(user):
    items = get_user_pantry(user)
    if hasattr(items, "select_related"):
        items = items.select_related("food")
    items = list(items)

    low = list(get_running_low_items(user))
    low_ids = {item.id for item in low}

    preview = sorted(items, key=lambda i: (i.id not in low_ids, i.food.name.lower()))[:PANTRY_PREVIEW]

    return {
        "items": items,
        "display": [
            {
                "name": item.food.name,
                "quantity": f"{_fmt_qty(item.quantity or 0)} {item.unit}",
                "is_low": item.id in low_ids,
            }
            for item in preview
        ],
        "total": len(items),
        "low_count": len(low),
        "expiring_count": len(list(get_expiring_items(user))),
        "expired_count": len(list(get_expired_items(user))),
    }


def _load_shopping(user):
    lists = get_user_shopping_lists(user)
    if hasattr(lists, "prefetch_related"):
        lists = lists.prefetch_related("items__food")
    lists = list(lists)

    if not lists:
        return EMPTY_SHOPPING

    # Prefer the list the meal planner fills with missing ingredients; else the newest.
    chosen = next((l for l in lists if l.name == SHOPPING_LIST_NAME), None) or max(lists, key=lambda l: l.id)

    rows = [
        {
            "id": item.id,
            "name": f"{item.food.name} — {_fmt_qty(item.quantity or 0)} {item.unit}",
            "checked": _flag(item, PURCHASED_FIELDS),
        }
        for item in chosen.items.all()
    ]
    rows.sort(key=lambda r: r["checked"])        # still-to-buy first (stable)

    return {
        "list": chosen,
        "rows": rows[:SHOPPING_PREVIEW],
        "count": len(rows),
        "pending": sum(1 for r in rows if not r["checked"]),
    }


def _load_plan(user, today):
    """Today's meals and the week overview, with pantry availability per meal."""
    stock = _pantry_stock(user)
    cache = {}

    def availability(schedule):
        key = (schedule.meal_id, schedule.servings)
        if key not in cache:
            cache[key] = _meal_availability(schedule.meal, schedule.servings, stock)
        return cache[key]

    week_start = get_week_start(today)
    week_end = get_week_end(today)

    schedules = list(
        get_user_schedule(user)
        .filter(date__gte=week_start, date__lte=week_end)
        .select_related("meal")
    )
    schedules.sort(key=lambda s: (s.date, _slot_order(s.meal_type)))

    today_meals = []
    for schedule in (s for s in schedules if s.date == today):
        info = availability(schedule)
        meal = schedule.meal

        detail_url = reverse("meals:meal_detail", kwargs={"meal_id": meal.id})
        if info["state"] == "unknown":
            detail_url += "#ingredients"          # nudge: this meal still needs ingredients

        today_meals.append({
            "slot": str(schedule.meal_type).replace("_", " ").title(),
            "name": meal.name,
            "image_url": _meal_image_url(meal),
            "url": detail_url,
            "meta": " · ".join(p for p in (_minutes_label(meal), _pantry_label(info)) if p),
            "is_done": _flag(schedule, DONE_FIELDS),
        })

    by_day = {}
    for schedule in schedules:
        by_day.setdefault(schedule.date, []).append(schedule)

    week_days = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        day_schedules = by_day.get(day, [])
        week_days.append({
            "label": f"{day:%a} {day.day}",
            "is_today": day == today,
            "meals": [s.meal.name for s in day_schedules],
            "planned": len({s.meal_type for s in day_schedules}),
            "total": len(MEAL_TYPES),
            "date": day.isoformat(),
        })

    states = [availability(s)["state"] for s in schedules]

    return {
        "today_meals": today_meals,
        "week_days": week_days,
        "planned": len(schedules),
        "ready": states.count("ready"),
        "with_data": len(states) - states.count("unknown"),
        "no_ingredients": states.count("unknown"),
        "empty_slots": 7 * len(MEAL_TYPES) - len(schedules),
    }


# =========================================================
# DERIVED CONTENT
# =========================================================

def _build_insights(plan, budget, pantry, shopping):
    insights = []

    if plan["planned"]:
        if plan["with_data"]:
            insights.append({
                "label": "Pantry",
                "text": (f"{plan['ready']} of {plan['with_data']} planned meal{_s(plan['with_data'])} "
                         f"this week can be made from your pantry."),
            })
        if plan["no_ingredients"]:
            n = plan["no_ingredients"]
            insights.append({
                "label": "Meals",
                "text": (f"{n} planned meal{_s(n)} {_have(n)} no ingredients yet, so pantry and "
                         f"shopping checks can't be done. Add ingredients to {'it' if n == 1 else 'them'}."),
            })
        if plan["empty_slots"]:
            n = plan["empty_slots"]
            insights.append({"label": "Planning", "text": f"{n} meal slot{_s(n)} still empty this week."})

    if budget:
        if budget["is_over"]:
            insights.append({"label": "Budget",
                             "text": f"You've spent {_kes(budget['spent'])} of your {_kes(budget['amount'])} budget."})
        elif budget["is_warning"]:
            insights.append({"label": "Budget",
                             "text": f"You've used {budget['percent_used']:.0f}% of your budget. "
                                     f"{_kes(budget['remaining'])} is left."})
        elif budget["days_remaining"] > 0 and budget["remaining"] > 0:
            per_day = budget["remaining"] / budget["days_remaining"]
            insights.append({"label": "Budget",
                             "text": f"{_kes(budget['remaining'])} left over {budget['days_remaining']} "
                                     f"day{_s(budget['days_remaining'])}: about {_kes(per_day)} a day."})

    if pantry["expired_count"]:
        n = pantry["expired_count"]
        insights.append({"label": "Pantry", "text": f"{n} pantry item{_s(n)} {_have(n)} expired."})
    elif pantry["expiring_count"]:
        n = pantry["expiring_count"]
        insights.append({"label": "Pantry", "text": f"{n} pantry item{_s(n)} will expire soon. Plan to use {'it' if n == 1 else 'them'}."})

    if shopping["pending"]:
        n = shopping["pending"]
        insights.append({"label": "Shopping",
                         "text": f"{n} item{_s(n)} still to buy on “{shopping['list'].name}”."})

    return insights[:INSIGHT_LIMIT]


def _build_notifications(budget, pantry):
    notes = []

    def add(text):
        notes.append({"text": text, "time_display": "Today", "is_unread": True})

    if pantry["expired_count"]:
        n = pantry["expired_count"]
        add(f"{n} pantry item{_s(n)} {_have(n)} expired.")
    if pantry["expiring_count"]:
        n = pantry["expiring_count"]
        add(f"{n} pantry item{_s(n)} will expire soon.")
    if pantry["low_count"]:
        n = pantry["low_count"]
        add(f"{n} pantry item{_s(n)} {'is' if n == 1 else 'are'} running low.")
    if budget and budget["is_over"]:
        add("You've gone over your budget.")
    elif budget and budget["is_warning"]:
        add("You're getting close to your budget limit.")

    return notes


def _build_activities(expenses, pantry, today):
    events = [(e.date, f"Recorded expense: {e.description} ({_kes(e.amount)})")
              for e in expenses[:ACTIVITY_LIMIT]]

    for item in pantry["items"]:
        acquired = getattr(item, "acquired_at", None)
        if acquired:
            if isinstance(acquired, datetime):
                acquired = acquired.date()
            events.append((acquired, f"Added {item.food.name} to your pantry"))

    events.sort(key=lambda event: event[0], reverse=True)

    return [{"text": text, "time_display": _relative_day(day, today)}
            for day, text in events[:ACTIVITY_LIMIT]]


# =========================================================
# VIEW
# =========================================================

@login_required
def dashboard(request):
    user = request.user
    now = timezone.localtime()
    today = now.date()

    budget, expenses = _safe(_load_budget, (None, []), user, today)
    pantry = _safe(_load_pantry, EMPTY_PANTRY, user)
    shopping = _safe(_load_shopping, EMPTY_SHOPPING, user)
    plan = _safe(_load_plan, EMPTY_PLAN, user, today)

    today_spent = sum((Decimal(e.amount) for e in expenses if e.date == today), Decimal("0"))

    meals_planned = len(plan["today_meals"])
    meals_total = len(MEAL_TYPES)

    notifications = _safe(_build_notifications, [], budget, pantry)

    return render(request, "dashboard.html", {
        "time_of_day": _time_of_day(now.hour),

        # Notifications (header bell)
        "notifications": notifications,
        "unread_notification_count": len(notifications),

        # Today's plan
        "today_meals": plan["today_meals"],
        "meals_planned_count": meals_planned,
        "meals_total_count": meals_total,
        "meals_progress_percent": int(meals_planned * 100 / meals_total) if meals_total else 0,
        "today_spent": today_spent,

        # Budget (dict, or None when no active budget)
        "budget": budget,

        # Shopping
        "shopping_list": shopping["list"],
        "shopping_items": shopping["rows"],
        "shopping_item_count": shopping["count"],
        "shopping_pending_count": shopping["pending"],

        # Pantry
        "pantry_items": pantry["display"],
        "pantry_total": pantry["total"],

        # Week, insights, activity
        "week_days": plan["week_days"],
        "insights": _safe(_build_insights, [], plan, budget, pantry, shopping),
        "activities": _safe(_build_activities, [], expenses, pantry, today),
    })
    
    
    
def intro(request):
    
    return render(request, "intro.html", {})


def login_user(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        
        # Check required fields
        if not username or not password:
            messages.error(
                request,
                "Please enter your username and password."
            )
            return redirect("login")
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            
            messages.success(request, ("Logged in successfully"))
            
            return redirect("dashboard")   
        
        else:
            messages.error(request, ("Incorrect username or password"))
            
            return redirect("login")           
        
    
    return render(request, "login.html", {})


def register(request):
    if request.method == "POST":
        full_name = request.POST.get("fullname", "").strip()
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        confirm_password = request.POST.get("confirm_password", "")

        # Check required fields
        if not all([full_name, username, email, password, confirm_password]):
            messages.error(request, "Fill in all the required fields!")
            return redirect("register")

        # Basic email validation
        if "@" not in email:
            messages.error(request, "Enter a valid email address.")
            return redirect("register")

        # Password length
        if len(password) < 8:
            messages.error(
                request,
                "Password must be at least 8 characters long."
            )
            return redirect("register")

        # Confirm password
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("register")

        # Username already exists
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
            return redirect("register")

        # Email already exists
        if User.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return redirect("register")

        # Split full name
        name_parts = full_name.split(maxsplit=1)

        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        # Create user
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
        )

        # Log the user in
        login(request, user)

        messages.success(request, "Account created successfully!")

        return redirect("login")

    return render(request, "register.html")

def logout_user(request):
    logout(request)
    
    messages.success(request, ("You have successfully logged out"))
    
    return redirect("intro")

        

def forgot_password(request):
    
    return render(request, "forgot-password.html", {})




def terms(request):
    
    return render(request, "terms.html", {})

def privacy(request):
    
    return render(request, "privacy.html", {})


def contact(request):
    if request.method == "POST":
        is_ajax = (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        topic = request.POST.get("topic", "").strip()
        message = request.POST.get("message", "").strip()
        username = request.POST.get("username", "").strip()

        errors = []

        if not full_name:
            errors.append({
                "field": "full_name",
                "message": "Please enter your full name.",
            })
        elif len(full_name) > 100:
            errors.append({
                "field": "full_name",
                "message": "Your name must be 100 characters or fewer.",
            })

        if not email:
            errors.append({
                "field": "email",
                "message": "Please enter your email address.",
            })
        else:
            try:
                validate_email(email)
            except ValidationError:
                errors.append({
                    "field": "email",
                    "message": "Please enter a valid email address.",
                })

        valid_topics = {
            value for value, label in Message.TopicChoices.choices
        }

        if topic not in valid_topics:
            errors.append({
                "field": "topic",
                "message": "Please select a valid topic.",
            })

        if not message:
            errors.append({
                "field": "message",
                "message": "Please enter your message.",
            })
        elif len(message) < 10:
            errors.append({
                "field": "message",
                "message": "Your message must contain at least 10 characters.",
            })
        elif len(message) > 5000:
            errors.append({
                "field": "message",
                "message": "Your message must be 5,000 characters or fewer.",
            })

        if errors:
            error_response = {
                "success": False,
                "message": "Please correct the errors and try again.",
                "errors": errors,
            }

            if is_ajax:
                return JsonResponse(error_response, status=400)

            for error in errors:
                messages.error(request, error["message"])

            return render(request, "contact.html", status=400)

        try:
            saved_message = Message.objects.create(
                full_name=full_name,
                email=email,
                topic=topic,
                message=message,
                username=username or None,
            )
        except Exception:
            # Log the real exception in the Django server terminal.
            import logging
            logging.getLogger(__name__).exception(
                "Failed to save contact message."
            )

            if is_ajax:
                return JsonResponse({
                    "success": False,
                    "message": (
                        "We couldn't save your message. "
                        "Please try again."
                    ),
                }, status=500)

            messages.error(
                request,
                "We couldn't save your message. Please try again.",
            )
            return redirect("contact")

        if is_ajax:
            return JsonResponse({
                "success": True,
                "message": "Your message has been received successfully!",
                "message_id": saved_message.pk,
            })

        messages.success(
            request,
            "Your message has been received successfully!",
        )
        return redirect("contact")

    return render(request, "contact.html")

def help(request):
    
    return render(request, "help.html", {})


def profile(request):
    print("AUTHENTICATED:", request.user.is_authenticated)
    print("CURRENT USER:", request.user)
    print("USER ID:", request.user.id)

    try:
        profile = Profile.objects.get(user=request.user)

        print("PROFILE:", profile)
        print("DISPLAY NAME:", profile.display_name)

        return render(request, "accounts/profile.html", {
            "profile": profile
        })
    except Exception as e:
        print(f"{str(e)}")
        logger.error(f"{str(e)}")
        
        return render(request, "accounts/profile.html")
    
    

# =====================================================================
# SETTINGS — replaces the existing `settings` view in apps/accounts/views.py
# (the one that accounts/urls.py already points at: path("settings/", views.settings, ...)).
#
# Add these imports at the top of views.py if they aren't there already.
# NOTE: the Django config is imported as `django_settings` because this view
# is itself called `settings`.
# =====================================================================

from django import forms
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

User = get_user_model()

SETTINGS_TEMPLATE = "accounts/settings.html"      # adjust to wherever the template lives


class ProfileSettingsForm(forms.ModelForm):
    """
    Only these three fields can ever be changed from this page, so privileged fields
    (is_staff, is_superuser, username, password, ...) can't be set by a crafted request.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        taken = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists()
        if taken:
            raise forms.ValidationError("That email address is already in use.")
        return email


def _settings_url(section):
    return f"{reverse('settings')}#{section}"



@login_required
@require_http_methods(["GET", "POST"])
def settings(request):
    """Account settings, including per-user Gemini API credentials."""

    user = request.user

    profile_form = ProfileSettingsForm(
        instance=User.objects.get(pk=user.pk)
    )

    can_change_password = user.has_usable_password()
    password_form = (
        PasswordChangeForm(user)
        if can_change_password
        else None
    )

    active_section = "profile"

    if request.method == "POST":
        action = request.POST.get("action", "").strip()

        # --------------------------------------------------
        # Profile settings
        # --------------------------------------------------
        if action == "profile":
            active_section = "profile"

            profile_form = ProfileSettingsForm(
                request.POST,
                instance=User.objects.get(pk=user.pk),
            )

            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Your profile was updated.")
                return redirect(_settings_url("profile"))

            messages.error(
                request,
                "Your profile wasn't saved. Please fix the highlighted fields.",
            )

        # --------------------------------------------------
        # Password settings
        # --------------------------------------------------
        elif action == "password" and can_change_password:
            active_section = "security"
            password_form = PasswordChangeForm(user, request.POST)

            if password_form.is_valid():
                updated_user = password_form.save()
                update_session_auth_hash(request, updated_user)

                messages.success(request, "Your password was changed.")
                return redirect(_settings_url("security"))

            messages.error(
                request,
                "Your password wasn't changed. Please fix the highlighted fields.",
            )

        # --------------------------------------------------
        # Save or test Gemini API credentials
        # --------------------------------------------------
        elif action in {"gemini_save", "gemini_test"}:
            active_section = "ai"
            config = get_user_ai_config(user)

            submitted_key = request.POST.get(
                "gemini_api_key", ""
            ).strip()

            model_name = request.POST.get(
                "model_name", config.model_name
            ).strip()

            if model_name not in GEMINI_MODELS:
                messages.error(
                    request,
                    "Choose a supported Gemini model.",
                )

            elif submitted_key:
                # Encrypt the API key before storing it.
                try:
                    encrypted_key = encrypt_api_key(submitted_key)
                except Exception:
                    logger.exception(
                        "Failed to encrypt a user's Gemini API key."
                    )
                    messages.error(
                        request,
                        "Secure key storage failed. Your API key was not saved.",
                    )
                else:
                    if action == "gemini_save":
                        config.encrypted_api_key = encrypted_key
                        config.model_name = model_name
                        config.connection_tested_at = None
                        config.connection_test_succeeded = False
                        config.connection_status = "untested"
                        config.save()

                        messages.success(
                            request,
                            "Your Gemini API key was saved securely. "
                            "Test the connection before chatting.",
                        )

                    else:
                        # Only replace the saved key after a successful test.
                        if test_user_api_key(
                            submitted_key, model_name
                        ):
                            config.encrypted_api_key = encrypted_key
                            config.model_name = model_name
                            config.connection_tested_at = timezone.now()
                            config.connection_test_succeeded = True
                            config.connection_status = "success"
                            config.save()

                            messages.success(
                                request,
                                "Gemini connected successfully. "
                                "Your API key was saved securely.",
                            )
                        else:
                            messages.error(
                                request,
                                "Gemini connection failed. Check your API key "
                                "and selected model. Your previously saved key "
                                "has not been replaced.",
                            )

            elif action == "gemini_test":
                # Test the existing saved key without exposing it to the browser.
                if not config.encrypted_api_key:
                    messages.error(
                        request,
                        "Enter a Gemini API key before testing the connection.",
                    )
                else:
                    try:
                        saved_key = decrypt_api_key(
                            config.encrypted_api_key
                        )
                    except Exception:
                        logger.exception(
                            "Failed to decrypt a user's Gemini API key."
                        )
                        messages.error(
                            request,
                            "Your saved API key could not be read. "
                            "Please save it again.",
                        )
                    else:
                        if test_user_api_key(
                            saved_key, model_name
                        ):
                            config.model_name = model_name
                            config.connection_tested_at = timezone.now()
                            config.connection_test_succeeded = True
                            config.connection_status = "success"
                            config.save()

                            messages.success(
                                request,
                                "Gemini connection test succeeded.",
                            )
                        else:
                            config.model_name = model_name
                            config.connection_tested_at = timezone.now()
                            config.connection_test_succeeded = False
                            config.connection_status = "failed"
                            config.save()

                            messages.error(
                                request,
                                "Gemini connection failed. Check your saved "
                                "key and selected model.",
                            )

            else:
                messages.error(
                    request,
                    "Enter a new API key to save it.",
                )

        # --------------------------------------------------
        # Remove saved Gemini API key
        # --------------------------------------------------
        elif action == "gemini_remove":
            active_section = "ai"
            config = get_user_ai_config(user)

            config.encrypted_api_key = ""
            config.connection_tested_at = None
            config.connection_test_succeeded = False
            config.connection_status = "untested"
            config.save()

            messages.success(
                request,
                "Your saved Gemini API key was removed.",
            )

        else:
            messages.error(
                request,
                "That action isn't available.",
            )

    # Always load the current user's AI configuration.
    ai_config = get_user_ai_config(user)

    return render(
        request,
        SETTINGS_TEMPLATE,
        {
            "profile_form": profile_form,
            "password_form": password_form,
            "account_user": user,
            "time_zone": getattr(django_settings, "TIME_ZONE", "UTC"),
            "active_section": active_section,
            "ai_config": ai_config,
            "gemini_models": GEMINI_MODELS,
        },
    )


# ---------------------------------------------------------------------
# Not implemented on purpose (the template says so instead of faking controls):
#   avatar / bio, language, food preferences, AI personalization, notification
#   preferences, data export, account deletion, active-session management.
# Each needs fields or services that aren't in the project yet.
# ---------------------------------------------------------------------