"""
Tests for apps/ai/services/tools.py.

No database is needed: the project's services are patched with small fakes, so these tests check
what the AI layer does with the data (scoping, validation, trimming, "propose never writes"),
not the services themselves. Adjust the import line below if the app lives elsewhere.
"""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.ai.services import actions, tools
from apps.ai.services.safety import ALWAYS_ALLOWED, PERMISSION_FIELDS, AIPermissions
from services.timetable import MEAL_TYPES

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
ALL = AIPermissions()


# ---------------------------------------------------------------- fakes

def make_user(pk=1):
    return SimpleNamespace(pk=pk, id=pk, is_authenticated=True, first_name="Wanjiru", profile=None)


def make_food(food_id, name):
    return SimpleNamespace(id=food_id, name=name, default_unit="g", is_perishable=False)


def pantry_item(item_id, food_id, name, qty, unit, expires=None):
    return SimpleNamespace(id=item_id, food_id=food_id, food=SimpleNamespace(name=name),
                           quantity=Decimal(qty), unit=unit, expires_at=expires)


def ingredient(food_id, name, qty, unit):
    return SimpleNamespace(food_id=food_id, food=SimpleNamespace(name=name), quantity=Decimal(qty), unit=unit)


class FakeQuerySet(list):
    """Enough of a queryset for the tools: filter() and select_related() return the same rows."""

    def filter(self, **kwargs):
        return self

    def select_related(self, *args):
        return self


# ---------------------------------------------------------------- declarations

class DeclarationTests(SimpleTestCase):

    def test_every_tool_is_well_formed(self):
        allowed_categories = set(PERMISSION_FIELDS) | set(ALWAYS_ALLOWED)
        for tool in tools.TOOLS.values():
            with self.subTest(tool=tool.name):
                self.assertTrue(tool.description.strip())
                self.assertTrue(tool.categories)
                self.assertTrue(set(tool.categories) <= allowed_categories)
                self.assertEqual(tool.parameters.get("type"), "object")

    def test_the_model_is_never_asked_for_a_user(self):
        for tool in tools.TOOLS.values():
            properties = set(tool.parameters.get("properties", {}))
            with self.subTest(tool=tool.name):
                self.assertFalse(properties & {"user", "user_id", "username", "email"})

    def test_there_are_no_direct_write_tools(self):
        for name in tools.TOOLS:
            with self.subTest(tool=name):
                self.assertFalse(name.startswith(("add_", "create_", "update_", "delete_", "remove_", "set_")))

    def test_disabled_categories_are_hidden_from_the_model(self):
        names = {d["name"] for d in tools.get_tool_declarations(AIPermissions(pantry=False))}
        self.assertNotIn("get_pantry_items", names)
        self.assertNotIn("check_meal_against_pantry", names)       # needs meals AND pantry
        self.assertIn("search_foods", names)                       # the food library holds no personal data
        self.assertIn("get_budget_summary", names)

    def test_tools_without_arguments_omit_parameters(self):
        by_name = {d["name"]: d for d in tools.get_tool_declarations(ALL)}
        self.assertNotIn("parameters", by_name["get_pantry_items"])
        self.assertIn("parameters", by_name["search_foods"])


# ---------------------------------------------------------------- dispatch rules

class DispatchTests(SimpleTestCase):

    def setUp(self):
        self.user = make_user()

    def test_unknown_tool(self):
        result = tools.dispatch(self.user, "drop_database", {}, ALL)
        self.assertFalse(result["ok"])

    def test_disabled_category_is_refused_before_any_service_runs(self):
        with patch.object(tools, "get_user_pantry") as pantry:
            result = tools.dispatch(self.user, "get_pantry_items", {}, AIPermissions(pantry=False))
        self.assertFalse(result["ok"])
        self.assertIn("turned off", result["error"])
        pantry.assert_not_called()

    def test_junk_arguments_are_tolerated(self):
        with patch.object(tools, "get_current_budget", return_value=None):
            result = tools.dispatch(self.user, "get_budget_summary", "not a dict", ALL)
        self.assertTrue(result["ok"])
        self.assertFalse(result["data"]["has_active_budget"])

    def test_unexpected_failures_do_not_leak_details(self):
        with patch.object(tools, "get_current_budget", side_effect=RuntimeError("secret internal detail")):
            result = tools.dispatch(self.user, "get_budget_summary", {}, ALL)
        self.assertFalse(result["ok"])
        self.assertNotIn("secret internal detail", str(result))


# ---------------------------------------------------------------- read tools

class PantryToolTests(SimpleTestCase):

    def setUp(self):
        self.user = make_user(pk=7)

    def test_uses_the_authenticated_user_and_ignores_a_user_id_argument(self):
        item = pantry_item(1, 10, "Beans", "500", "g", expires=timezone.localdate() + timedelta(days=2))
        with patch.object(tools, "get_user_pantry", return_value=[item]) as pantry, \
             patch.object(tools, "get_running_low_items", return_value=[]):
            result = tools.dispatch(self.user, "get_pantry_items", {"user_id": 99}, ALL)

        pantry.assert_called_once_with(self.user)
        row = result["data"]["items"][0]
        self.assertEqual((row["food"], row["quantity"], row["unit"]), ("Beans", 500, "g"))
        self.assertEqual(row["days_until_expiry"], 2)
        self.assertFalse(row["running_low"])

    def test_marks_items_that_are_running_low(self):
        item = pantry_item(1, 10, "Rice", "1", "kg")
        with patch.object(tools, "get_user_pantry", return_value=[item]), \
             patch.object(tools, "get_running_low_items", return_value=[item]):
            result = tools.dispatch(self.user, "get_pantry_items", {}, ALL)
        self.assertTrue(result["data"]["items"][0]["running_low"])

    def test_expiry_window_defaults_to_seven_days_and_is_bounded(self):
        with patch.object(tools, "get_expiring_items", return_value=[]) as expiring, \
             patch.object(tools, "get_expired_items", return_value=[]):
            ok = tools.dispatch(self.user, "get_expiring_pantry_items", {}, ALL)
            bad = tools.dispatch(self.user, "get_expiring_pantry_items", {"days": 999}, ALL)

        self.assertTrue(ok["ok"])
        expiring.assert_called_once_with(self.user, days=7)
        self.assertFalse(bad["ok"])


class FoodAndMealToolTests(SimpleTestCase):

    def setUp(self):
        self.user = make_user()

    def test_search_foods_needs_a_query(self):
        self.assertFalse(tools.dispatch(self.user, "search_foods", {}, ALL)["ok"])

    def test_search_foods_returns_ids_the_model_can_use(self):
        with patch.object(tools, "search_food_library", return_value=[make_food(4, "Tomato")]):
            result = tools.dispatch(self.user, "search_foods", {"query": "tom"}, ALL)
        self.assertEqual(result["data"]["foods"][0]["food_id"], 4)

    def test_meal_details_reject_missing_and_invalid_ids(self):
        with patch.object(tools, "get_user_available_meal", return_value=None):
            self.assertFalse(tools.dispatch(self.user, "get_meal_details", {"meal_id": 5}, ALL)["ok"])
        self.assertFalse(tools.dispatch(self.user, "get_meal_details", {"meal_id": "abc"}, ALL)["ok"])
        self.assertFalse(tools.dispatch(self.user, "get_meal_details", {}, ALL)["ok"])

    def test_long_stored_text_is_trimmed_before_the_model_sees_it(self):
        meal = SimpleNamespace(id=1, name="Githeri", description="x" * 1000, instructions="y" * 3000,
                               prep_time=10, cook_time=40)
        with patch.object(tools, "get_user_available_meal", return_value=meal), \
             patch.object(tools, "get_meal_ingredients", return_value=[]):
            data = tools.dispatch(self.user, "get_meal_details", {"meal_id": 1}, ALL)["data"]
        self.assertLessEqual(len(data["description"]), 300)
        self.assertLessEqual(len(data["instructions"]), 900)
        self.assertFalse(data["has_ingredients"])

    def test_pantry_check_reports_what_is_missing(self):
        meal = SimpleNamespace(id=1, name="Beans and ugali")
        meal_ingredients = [ingredient(1, "Beans", "500", "g"), ingredient(2, "Salt", "1", "packet")]
        stock = [pantry_item(1, 1, "Beans", "200", "g"), pantry_item(2, 2, "Salt", "50", "g")]

        with patch.object(tools, "get_user_available_meal", return_value=meal), \
             patch.object(tools, "get_meal_ingredients", return_value=meal_ingredients), \
             patch.object(tools, "get_user_pantry", return_value=stock):
            one = tools.dispatch(self.user, "check_meal_against_pantry", {"meal_id": 1}, ALL)["data"]
            two = tools.dispatch(self.user, "check_meal_against_pantry", {"meal_id": 1, "servings": 2}, ALL)["data"]

        self.assertEqual(one["state"], "missing")
        self.assertEqual(one["missing"][0]["food"], "Beans")
        self.assertEqual(one["missing"][0]["still_needed"], 300)            # 500 needed - 200 held
        self.assertEqual(one["missing"][1]["food"], "Salt")
        self.assertEqual(one["missing"][1]["still_needed"], 1)
        self.assertEqual(one["assumed_available_but_unit_differs"][0]["food"], "Salt")
        self.assertEqual(two["missing"][0]["still_needed"], 800)            # 1000 needed - 200 held

    def test_pantry_check_says_when_a_meal_has_no_ingredients(self):
        with patch.object(tools, "get_user_available_meal", return_value=SimpleNamespace(id=1, name="Plain")), \
             patch.object(tools, "get_meal_ingredients", return_value=[]), \
             patch.object(tools, "get_user_pantry", return_value=[]):
            data = tools.dispatch(self.user, "check_meal_against_pantry", {"meal_id": 1}, ALL)["data"]
        self.assertEqual(data["state"], "unknown")


class PlanBudgetShoppingToolTests(SimpleTestCase):

    def setUp(self):
        self.user = make_user()

    def test_meal_plan_rejects_bad_ranges(self):
        self.assertFalse(tools.dispatch(self.user, "get_meal_plan",
                                        {"start_date": "2026-10-10", "end_date": "2026-10-01"}, ALL)["ok"])
        self.assertFalse(tools.dispatch(self.user, "get_meal_plan",
                                        {"start_date": "2026-01-01", "end_date": "2026-06-01"}, ALL)["ok"])
        self.assertFalse(tools.dispatch(self.user, "get_meal_plan", {"start_date": "tomorrow"}, ALL)["ok"])

    def test_meal_plan_returns_rows(self):
        schedule = SimpleNamespace(date=timezone.localdate(), meal_type="lunch",
                                   meal=SimpleNamespace(name="Githeri"), meal_id=3, servings=2)
        with patch.object(tools, "get_user_schedule", return_value=FakeQuerySet([schedule])) as plan:
            data = tools.dispatch(self.user, "get_meal_plan", {}, ALL)["data"]
        plan.assert_called_once_with(self.user)
        self.assertEqual(data["planned"][0]["meal"], "Githeri")

    def test_budget_without_an_active_budget(self):
        with patch.object(tools, "get_current_budget", return_value=None):
            data = tools.dispatch(self.user, "get_budget_summary", {}, ALL)["data"]
        self.assertFalse(data["has_active_budget"])

    def test_budget_summary(self):
        today = timezone.localdate()
        budget = SimpleNamespace(name="October food", amount=Decimal("10000"),
                                 start_date=today - timedelta(days=10), end_date=today + timedelta(days=20))
        with patch.object(tools, "get_current_budget", return_value=budget), \
             patch.object(tools, "get_total_spent", return_value=Decimal("2500")), \
             patch.object(tools, "get_remaining_budget", return_value=Decimal("7500")), \
             patch.object(tools, "get_budget_expenses", return_value=[]):
            data = tools.dispatch(self.user, "get_budget_summary", {}, ALL)["data"]

        self.assertEqual((data["budget_amount"], data["spent"], data["remaining"]), (10000, 2500, 7500))
        self.assertEqual(data["percent_used"], 25)
        self.assertEqual(data["days_left"], 20)

    def test_shopping_lists(self):
        item = SimpleNamespace(food=SimpleNamespace(name="Onions"), quantity=Decimal("2"), unit="kg", is_purchased=False)
        shopping_list = SimpleNamespace(id=9, name="Weekly", items=SimpleNamespace(all=lambda: [item]))
        with patch.object(tools, "get_user_shopping_lists", return_value=[shopping_list]) as lists:
            data = tools.dispatch(self.user, "get_shopping_lists", {}, ALL)["data"]
        lists.assert_called_once_with(self.user)
        self.assertEqual(data["lists"][0]["still_to_buy"], 1)


# ---------------------------------------------------------------- proposals never write

@override_settings(CACHES=LOCMEM)
class ProposalToolTests(SimpleTestCase):

    def setUp(self):
        cache.clear()
        self.user = make_user()

    def _propose_shopping(self, items, **patches):
        with patch.object(actions, "get_food_by_id", return_value=make_food(1, "Tomato")), \
             patch.object(actions, "get_user_shopping_lists", return_value=[]), \
             patch.object(actions, "create_shopping_list") as create, \
             patch.object(actions, "add_shopping_item") as add:
            result = tools.dispatch(self.user, "propose_add_to_shopping_list", {"items": items}, ALL)
        return result, create, add

    def test_shopping_proposal_waits_for_confirmation_and_writes_nothing(self):
        result, create, add = self._propose_shopping([{"food_id": 1, "quantity": 2, "unit": "kg"}])

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["status"], "waiting_for_user_confirmation")
        self.assertTrue(result["data"]["pending_action"]["id"])
        create.assert_not_called()
        add.assert_not_called()

    def test_shopping_proposal_validation(self):
        bad_inputs = [
            [{"food_id": 1, "quantity": 2, "unit": "bags"}],        # unknown unit
            [{"food_id": 1, "quantity": -1, "unit": "kg"}],         # negative quantity
            [{"food_id": 1, "quantity": "lots", "unit": "kg"}],     # not a number
            [{"food_id": "x", "quantity": 1, "unit": "kg"}],        # bad id
            [],                                                     # nothing to add
            [{"food_id": 1, "quantity": 1, "unit": "kg"}] * 26,     # too many
        ]
        for items in bad_inputs:
            with self.subTest(items=str(items)[:60]):
                result, _create, add = self._propose_shopping(items)
                self.assertFalse(result["ok"])
                add.assert_not_called()

    def test_unknown_food_is_rejected(self):
        with patch.object(actions, "get_food_by_id", return_value=None):
            result = tools.dispatch(self.user, "propose_add_to_shopping_list",
                                    {"items": [{"food_id": 404, "quantity": 1, "unit": "kg"}]}, ALL)
        self.assertFalse(result["ok"])

    def test_meal_proposal_waits_for_confirmation_and_writes_nothing(self):
        meal = SimpleNamespace(id=3, name="Githeri")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        with patch.object(actions, "get_user_available_meal", return_value=meal), \
             patch.object(actions, "schedule_meal") as schedule:
            result = tools.dispatch(self.user, "propose_schedule_meal", {
                "meal_id": 3, "date": tomorrow, "meal_type": list(MEAL_TYPES)[0], "servings": 2}, ALL)

        self.assertEqual(result["data"]["status"], "waiting_for_user_confirmation")
        schedule.assert_not_called()

    def test_meal_proposal_validation(self):
        meal = SimpleNamespace(id=3, name="Githeri")
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        first_type = list(MEAL_TYPES)[0]

        bad_inputs = [
            {"meal_id": 3, "date": yesterday, "meal_type": first_type},
            {"meal_id": 3, "date": "soon", "meal_type": first_type},
            {"meal_id": 3, "date": tomorrow, "meal_type": "brunch-for-twelve"},
            {"meal_id": 3, "date": tomorrow, "meal_type": first_type, "servings": 0},
            {"meal_id": 3, "date": tomorrow, "meal_type": first_type, "servings": 500},
        ]
        for args in bad_inputs:
            with self.subTest(args=args), patch.object(actions, "get_user_available_meal", return_value=meal):
                self.assertFalse(tools.dispatch(self.user, "propose_schedule_meal", args, ALL)["ok"])

        with patch.object(actions, "get_user_available_meal", return_value=None):
            missing = tools.dispatch(self.user, "propose_schedule_meal",
                                     {"meal_id": 99, "date": tomorrow, "meal_type": first_type}, ALL)
        self.assertFalse(missing["ok"])