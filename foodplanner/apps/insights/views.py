"""
apps/insights/views.py

One page: /insights/ . All calculation lives in apps/insights/analytics.py
(the module that defines build_insights_page); this view only reads the
request, supplies URL lookups, and renders the template.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from .analytics import PERIOD_OPTIONS, build_insights_page, resolve_period

logger = logging.getLogger(__name__)

TEMPLATE = "insights/insights.html"


def _links(name, *args):
    """
    URL lookup handed to the analytics module.

    Returns None when a route doesn't exist, so that action button is simply
    left out instead of the whole page failing with NoReverseMatch.
    """
    try:
        return reverse(name, args=args)
    except NoReverseMatch:
        logger.warning("Insights: no URL named %r (args=%r)", name, args)
        return None


@login_required
@require_GET
def insights_page(request):
    """
    Insights for the logged-in user.

    Query string:
        ?period=this_week | this_month | last_month | last_30 | last_90 | custom
        &start=YYYY-MM-DD&end=YYYY-MM-DD      (only used with period=custom)

    An unknown period falls back to this month; an invalid custom range falls back
    too and the page shows period.error explaining why.
    """
    today = timezone.localdate()

    period_key = request.GET.get("period", "this_month")
    custom_start = request.GET.get("start", "")
    custom_end = request.GET.get("end", "")

    try:
        page = build_insights_page(
            user=request.user,
            today=today,
            period_key=period_key,
            custom_start=custom_start,
            custom_end=custom_end,
            links=_links,
        )
    except Exception:
        # Each section is already isolated inside the analytics module, so this only
        # triggers if something outside a section breaks. Show an empty page, not a 500.
        logger.exception("Insights page failed for user %s", request.user.pk)
        messages.error(request, "We couldn't load your insights right now. Please try again.")
        page = {
            "period": resolve_period("this_month", today),
            "periods": PERIOD_OPTIONS,
            "ask_url": _links("ai:page"),
            "overview": [],
            "insights": [],
            "spending": None,
            "budgets": None,
            "shopping": None,
            "pantry": None,
            "meals": None,
            "unavailable": ["spending", "shopping", "pantry", "meals"],
        }

    # Sections are available both flat (spending, pantry, ...) and as `page`.
    return render(request, TEMPLATE, {**page, "page": page, "today": today})