from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Budget, BudgetEntry


class BudgetPaginationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="budget-reader",
            email="budget-reader@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.user)
        today = date.today()
        self.budget = Budget.objects.create(
            user=self.user,
            name="Current food budget",
            amount=Decimal("1000"),
            start_date=today - timedelta(days=10),
            end_date=today + timedelta(days=10),
        )
        for number in range(17):
            BudgetEntry.objects.create(
                budget=self.budget,
                description=f"Expense {number:02}",
                amount=Decimal("10"),
                date=today,
            )

    def test_budget_detail_paginates_expenses_with_graceful_page_bounds(self):
        response = self.client.get(
            reverse("budgets:detail", args=[self.budget.pk]),
            {"page": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["expense_count"], 17)
        self.assertEqual(len(response.context["expenses"]), 2)
        self.assertEqual(
            response.context["budget_insights"][1],
            "You've recorded 17 expenses, averaging KES 10 each.",
        )

        filtered = self.client.get(
            reverse("budgets:detail", args=[self.budget.pk]),
            {"expense_q": "Expense 16"},
        )
        self.assertEqual(filtered.context["expense_count"], 1)
        self.assertEqual(filtered.context["expenses"][0].description, "Expense 16")

        out_of_range = self.client.get(
            reverse("budgets:detail", args=[self.budget.pk]),
            {"page": "999"},
        )
        self.assertEqual(out_of_range.context["page_obj"].number, 2)
