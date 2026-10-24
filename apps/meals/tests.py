from datetime import date, timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.foods.models import Food, FoodCategory
from apps.meals.models import (
    Meal,
    MealConsumption,
    MealConsumptionItem,
    MealIngredient,
    MealSchedule,
    UserMealPreference,
)
from apps.pantry.models import PantryItem
from apps.shopping.models import ShoppingItem, ShoppingList
from services.meals import (
    add_meal_ingredient,
    get_user_available_meals,
    mark_scheduled_meal_cooked,
    move_scheduled_meal,
    remove_scheduled_meal,
    schedule_meal,
    update_servings,
)
from services.timetable import MEAL_TYPES, create_weekly_timetable, get_week_start


class MealPlanningWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="planner",
            email="planner@example.com",
            password="test-password",
        )
        self.other_user = user_model.objects.create_user(
            username="other",
            email="other@example.com",
            password="test-password",
        )
        category = FoodCategory.objects.create(name="Produce")
        self.food = Food.objects.create(name="Tomato", category=category)
        self.meal = Meal.objects.create(name="Tomato soup")
        self.other_meal = Meal.objects.create(name="Beans and rice")
        self.client.force_login(self.user)

    def test_library_uses_user_scoped_archives_and_favorites(self):
        favorite_response = self.client.post(
            reverse("meals:toggle_favorite", args=[self.meal.pk]),
            {"next": reverse("meals:favorite_meals")},
        )
        self.assertRedirects(favorite_response, reverse("meals:favorite_meals"))
        self.assertTrue(
            UserMealPreference.objects.get(user=self.user, meal=self.meal).is_favorite
        )

        self.client.post(reverse("meals:archive_meal", args=[self.meal.pk]))
        self.assertNotIn(self.meal, get_user_available_meals(self.user))
        self.assertIn(self.meal, get_user_available_meals(self.other_user))

        archived_response = self.client.get(reverse("meals:archived_meals"))
        self.assertEqual(archived_response.status_code, 200)
        self.assertContains(archived_response, self.meal.name)

        restore_response = self.client.post(
            reverse("meals:restore_meal", args=[self.meal.pk])
        )
        self.assertEqual(restore_response.status_code, 302)
        self.assertIn(self.meal, get_user_available_meals(self.user))

    def test_meal_detail_and_library_render_favorite_state(self):
        UserMealPreference.objects.create(
            user=self.user,
            meal=self.meal,
            is_favorite=True,
        )

        library_response = self.client.get(reverse("meals:meal_library"))
        self.assertEqual(library_response.status_code, 200)
        self.assertContains(library_response, self.meal.name)

        detail_response = self.client.get(
            reverse("meals:meal_detail", args=[self.meal.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertTrue(detail_response.context["is_favorite"])

    def test_meal_pagination_preserves_search_and_stable_sort_order(self):
        for number in range(13):
            Meal.objects.create(name=f"Paged meal {number:02}")

        response = self.client.get(
            reverse("meals:meal_library"),
            {"q": "Paged meal", "sort": "za", "page": "2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["meal_total_count"], 13)
        self.assertEqual(
            [meal.name for meal in response.context["meals"]],
            ["Paged meal 00"],
        )
        self.assertIn("q=Paged+meal", response.context["page_query"])
        self.assertIn("sort=za", response.context["page_query"])

    def test_meal_library_route_and_create_add_ingredient_flow(self):
        self.assertEqual(reverse("meals:meal_library"), "/meals/")
        legacy_response = self.client.get("/meals/meals/?q=soup")
        self.assertRedirects(
            legacy_response,
            "/meals/?q=soup",
            fetch_redirect_response=False,
        )

        create_response = self.client.post(
            reverse("meals:create_meal"),
            {
                "name": "Tomato stew",
                "description": "A quick meal",
                "instructions": "Cook the tomatoes.",
                "prep_time": "10",
                "cook_time": "20",
            },
        )
        created_meal = Meal.objects.get(name="Tomato stew")
        self.assertRedirects(
            create_response,
            reverse("meals:meal_detail", args=[created_meal.pk]) + "#ingredients",
            fetch_redirect_response=False,
        )

        ingredient_response = self.client.post(
            reverse("meals:add_ingredient", args=[created_meal.pk]),
            {
                "food_id": str(self.food.pk),
                "quantity": "2.5",
                "unit": "piece",
            },
        )
        self.assertEqual(ingredient_response.status_code, 302)
        ingredient = MealIngredient.objects.get(meal=created_meal, food=self.food)
        self.assertEqual(ingredient.quantity, Decimal("2.50"))

        detail_response = self.client.get(
            reverse("meals:meal_detail", args=[created_meal.pk])
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Tomato")

    def test_planner_supports_each_model_meal_type(self):
        self.assertEqual(MEAL_TYPES, tuple(MealSchedule.MealType.values))

        plan = create_weekly_timetable(
            meal_options={meal_type: [self.meal] for meal_type in MEAL_TYPES},
            start_date=get_week_start(date.today()),
            reuse_lunch=False,
        )
        self.assertEqual(len(plan), 7)
        self.assertEqual(
            set(next(iter(plan.values()))),
            set(MEAL_TYPES),
        )
        self.assertTrue(all(day["snack"] == self.meal for day in plan.values()))

        response = self.client.get(reverse("meals:timetable"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Snack")

    def test_schedule_service_supports_snack_and_rejects_archived_meal(self):
        schedule = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.SNACK,
            servings=2,
        )
        self.assertEqual(schedule.meal_type, MealSchedule.MealType.SNACK)
        self.assertEqual(schedule.servings, 2)

        with self.assertRaisesMessage(ValueError, "whole number"):
            schedule_meal(
                self.user,
                self.meal,
                date.today(),
                MealSchedule.MealType.LUNCH,
                servings=Decimal("1.5"),
            )

        UserMealPreference.objects.create(
            user=self.user,
            meal=self.other_meal,
            is_archived=True,
        )
        with self.assertRaisesMessage(ValueError, "archived"):
            schedule_meal(
                self.user,
                self.other_meal,
                date.today(),
                MealSchedule.MealType.LUNCH,
            )

    def test_adding_meal_to_timetable_does_not_deduct_pantry_stock(self):
        MealIngredient.objects.create(
            meal=self.meal,
            food=self.food,
            quantity=Decimal("2"),
            unit="g",
        )
        pantry = PantryItem.objects.create(
            user=self.user,
            food=self.food,
            quantity=Decimal("10"),
            unit="g",
        )

        schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.BREAKFAST,
            servings=2,
        )

        pantry.refresh_from_db()
        self.assertEqual(pantry.quantity, Decimal("10.00"))
        self.assertFalse(MealConsumption.objects.exists())

    def test_schedule_view_does_not_replace_an_occupied_slot(self):
        existing = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.BREAKFAST,
        )
        response = self.client.post(
            reverse("meals:schedule_meal"),
            {
                "meal_id": self.other_meal.pk,
                "date": existing.date.isoformat(),
                "meal_type": existing.meal_type,
                "servings": "3",
            },
        )

        self.assertEqual(response.status_code, 302)
        existing.refresh_from_db()
        self.assertEqual(existing.meal, self.meal)
        self.assertEqual(existing.servings, 1)
        self.assertEqual(MealSchedule.objects.filter(user=self.user).count(), 1)

    def test_move_rejects_occupied_target_without_overwriting_either_meal(self):
        source = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.BREAKFAST,
        )
        target = schedule_meal(
            self.user,
            self.other_meal,
            date.today() + timedelta(days=1),
            MealSchedule.MealType.LUNCH,
        )

        with self.assertRaisesMessage(ValueError, "already occupied"):
            move_scheduled_meal(
                self.user,
                source.pk,
                target.date,
                target.meal_type,
            )

        source.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual(source.meal, self.meal)
        self.assertEqual(target.meal, self.other_meal)

    def test_daily_route_redirects_to_week_containing_requested_date(self):
        selected_date = date(2026, 10, 21)
        response = self.client.get(
            reverse("meals:daily_timetable"),
            {"date": selected_date.isoformat()},
        )
        self.assertRedirects(
            response,
            f"{reverse('meals:timetable')}?date={selected_date.isoformat()}",
            fetch_redirect_response=False,
        )

    def test_ingredient_service_rejects_nonpositive_and_excess_precision(self):
        for quantity in (Decimal("0"), Decimal("-1"), Decimal("0.001")):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    add_meal_ingredient(self.meal, self.food, quantity, "piece")

        ingredient = add_meal_ingredient(
            self.meal,
            self.food,
            Decimal("1.25"),
            "piece",
        )
        self.assertEqual(ingredient.quantity, Decimal("1.25"))
        self.assertEqual(MealIngredient.objects.count(), 1)

    def test_shopping_handoff_is_idempotent_for_missing_ingredients(self):
        add_meal_ingredient(self.meal, self.food, Decimal("2"), "piece")
        schedule = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.LUNCH,
        )
        url = reverse("meals:add_missing_to_shopping", args=[schedule.pk])

        self.client.post(url)
        self.client.post(url)

        self.assertEqual(ShoppingList.objects.filter(user=self.user).count(), 1)
        self.assertEqual(ShoppingItem.objects.filter(shopping_list__user=self.user).count(), 1)


class MealCookingWorkflowTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="cook",
            email="cook@example.com",
            password="test-password",
        )
        self.other_user = user_model.objects.create_user(
            username="other-cook",
            email="other-cook@example.com",
            password="test-password",
        )
        category = FoodCategory.objects.create(name="Cooking")
        self.food = Food.objects.create(name="Rice", category=category)
        self.other_food = Food.objects.create(name="Beans", category=category)
        self.meal = Meal.objects.create(name="Rice and beans")
        self.schedule = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.LUNCH,
            servings=2,
        )

    def add_ingredient(self, food, quantity, unit):
        return MealIngredient.objects.create(
            meal=self.meal,
            food=food,
            quantity=Decimal(quantity),
            unit=unit,
        )

    def add_pantry(self, food, quantity, unit):
        return PantryItem.objects.create(
            user=self.user,
            food=food,
            quantity=Decimal(quantity),
            unit=unit,
        )

    def test_cooking_deducts_per_serving_ingredients_times_scheduled_servings(self):
        self.add_ingredient(self.food, "100", "g")
        pantry = self.add_pantry(self.food, "250", "g")

        cooked = mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        pantry.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertTrue(cooked.is_cooked)
        self.assertEqual(pantry.quantity, Decimal("50.00"))
        self.assertTrue(self.schedule.is_cooked)
        self.assertIsNotNone(self.schedule.cooked_at)
        self.assertEqual(
            list(MealConsumptionItem.objects.values_list("quantity", "unit")),
            [(Decimal("200.00"), "g")],
        )

    def test_mixed_kg_and_g_stock_is_allocated_exactly(self):
        self.add_ingredient(self.food, "250", "g")
        self.schedule.servings = 2
        self.schedule.save(update_fields=["servings"])
        kg = self.add_pantry(self.food, "0.30", "kg")
        grams = self.add_pantry(self.food, "200", "g")

        mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        self.assertFalse(PantryItem.objects.filter(pk=kg.pk).exists())
        self.assertFalse(PantryItem.objects.filter(pk=grams.pk).exists())
        self.assertEqual(
            set(MealConsumptionItem.objects.values_list("quantity", "unit")),
            {(Decimal("0.30"), "kg"), (Decimal("200.00"), "g")},
        )

    def test_litres_and_millilitres_are_compatible(self):
        self.add_ingredient(self.food, "300", "ml")
        self.add_pantry(self.food, "0.80", "l")

        mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        self.assertEqual(PantryItem.objects.get(food=self.food).quantity, Decimal("0.20"))

    def test_planner_availability_uses_the_same_unit_and_serving_calculation(self):
        self.add_ingredient(self.food, "100", "g")
        self.add_pantry(self.food, "0.20", "kg")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("meals:timetable"),
            {"date": self.schedule.date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ready to cook")
        self.assertContains(response, "Mark as Cooked / Eaten")

    def test_timetable_shows_required_and_available_missing_quantities(self):
        self.add_ingredient(self.food, "100", "g")
        self.add_pantry(self.food, "50", "g")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("meals:timetable"),
            {"date": self.schedule.date.isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rice — 200 g required, 50 g available")

    def test_incompatible_units_are_rejected_without_deduction(self):
        self.add_ingredient(self.food, "1", "kg")
        pantry = self.add_pantry(self.food, "5", "piece")

        with self.assertRaisesMessage(ValueError, "incompatible units"):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        pantry.refresh_from_db()
        self.assertEqual(pantry.quantity, Decimal("5.00"))
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cooked)

    def test_multiple_compatible_pantry_records_supply_one_ingredient(self):
        self.add_ingredient(self.food, "1", "kg")
        self.schedule.servings = 1
        self.schedule.save(update_fields=["servings"])
        smaller_unit = self.add_pantry(self.food, "0.40", "kg")
        larger_unit = self.add_pantry(self.food, "600", "g")

        mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        self.assertFalse(PantryItem.objects.filter(pk=smaller_unit.pk).exists())
        self.assertFalse(PantryItem.objects.filter(pk=larger_unit.pk).exists())
        self.assertEqual(MealConsumptionItem.objects.count(), 2)

    def test_insufficient_ingredient_leaves_all_pantry_records_unchanged(self):
        self.add_ingredient(self.food, "100", "g")
        self.add_ingredient(self.other_food, "50", "g")
        rice = self.add_pantry(self.food, "500", "g")
        beans = self.add_pantry(self.other_food, "25", "g")

        with self.assertRaisesMessage(ValueError, "insufficient compatible stock"):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        rice.refresh_from_db()
        beans.refresh_from_db()
        self.assertEqual(rice.quantity, Decimal("500.00"))
        self.assertEqual(beans.quantity, Decimal("25.00"))
        self.assertFalse(MealConsumption.objects.exists())
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cooked)

    def test_meal_without_ingredients_cannot_be_cooked(self):
        with self.assertRaisesMessage(ValueError, "no ingredients"):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cooked)

    def test_missing_pantry_ingredient_is_reported_without_partial_deduction(self):
        self.add_ingredient(self.food, "100", "g")
        rice = self.add_pantry(self.other_food, "500", "g")

        with self.assertRaisesMessage(
            ValueError,
            "Missing pantry ingredient: Rice requires 200 g; available 0 g.",
        ):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        rice.refresh_from_db()
        self.assertEqual(rice.quantity, Decimal("500.00"))
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cooked)
        self.assertFalse(MealConsumption.objects.exists())

    def test_failure_recording_consumption_rolls_back_stock_and_cooked_state(self):
        self.add_ingredient(self.food, "100", "g")
        pantry = self.add_pantry(self.food, "500", "g")

        with patch(
            "services.meals.MealConsumptionItem.objects.create",
            side_effect=RuntimeError("simulated consumption-record failure"),
        ):
            with self.assertRaisesMessage(RuntimeError, "simulated consumption-record failure"):
                mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        pantry.refresh_from_db()
        self.schedule.refresh_from_db()
        self.assertEqual(pantry.quantity, Decimal("500.00"))
        self.assertFalse(self.schedule.is_cooked)
        self.assertFalse(MealConsumption.objects.exists())

    def test_user_cannot_cook_another_users_schedule(self):
        self.add_ingredient(self.food, "1", "g")
        self.add_pantry(self.food, "10", "g")

        with self.assertRaisesMessage(ValueError, "not found"):
            mark_scheduled_meal_cooked(self.other_user, self.schedule.pk)

        self.assertFalse(MealConsumption.objects.exists())

    def test_cooking_endpoint_is_post_only_and_owner_scoped(self):
        self.add_ingredient(self.food, "1", "g")
        self.add_pantry(self.food, "10", "g")
        self.client.force_login(self.user)
        url = reverse("meals:cook_meal_schedule", args=[self.schedule.pk])

        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url, {"week": date.today().isoformat()})
        self.assertEqual(response.status_code, 302)
        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_cooked)

    def test_repeat_cooking_does_not_deduct_twice(self):
        self.add_ingredient(self.food, "100", "g")
        pantry = self.add_pantry(self.food, "500", "g")
        mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        with self.assertRaisesMessage(ValueError, "already been cooked"):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        pantry.refresh_from_db()
        self.assertEqual(pantry.quantity, Decimal("300.00"))
        self.assertEqual(MealConsumption.objects.count(), 1)

    def test_unrepresentable_requirement_is_rejected_exactly(self):
        self.add_ingredient(self.food, "0.01", "g")
        pantry = self.add_pantry(self.food, "1", "kg")

        with self.assertRaisesMessage(ValueError, "cannot represent the required quantity exactly"):
            mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        pantry.refresh_from_db()
        self.assertEqual(pantry.quantity, Decimal("1.00"))
        self.assertFalse(MealConsumption.objects.exists())

    def test_cooked_schedule_cannot_be_changed_or_overwritten_by_generation(self):
        self.add_ingredient(self.food, "1", "g")
        self.add_pantry(self.food, "10", "g")
        mark_scheduled_meal_cooked(self.user, self.schedule.pk)

        with self.assertRaisesMessage(ValueError, "already been cooked"):
            schedule_meal(
                self.user,
                self.meal,
                self.schedule.date,
                self.schedule.meal_type,
                servings=3,
            )
        with self.assertRaisesMessage(ValueError, "already been cooked"):
            update_servings(self.user, self.schedule.pk, 3)
        with self.assertRaisesMessage(ValueError, "already been cooked"):
            move_scheduled_meal(
                self.user,
                self.schedule.pk,
                self.schedule.date + timedelta(days=1),
                self.schedule.meal_type,
            )
        with self.assertRaisesMessage(ValueError, "already been cooked"):
            remove_scheduled_meal(self.user, self.schedule.pk)

        self.client.force_login(self.user)
        response = self.client.post(
            reverse("meals:generate_timetable"),
            {"date": get_week_start(self.schedule.date).isoformat()},
        )
        self.assertEqual(response.status_code, 302)
        self.schedule.refresh_from_db()
        self.assertTrue(self.schedule.is_cooked)
        self.assertEqual(self.schedule.servings, 2)
        self.assertEqual(self.schedule.meal, self.meal)

    def test_new_schedules_default_to_uncooked(self):
        self.schedule.refresh_from_db()
        self.assertFalse(self.schedule.is_cooked)
        self.assertIsNone(self.schedule.cooked_at)


class ConcurrentMealCookingTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="concurrent-cook",
            email="concurrent-cook@example.com",
            password="test-password",
        )
        category = FoodCategory.objects.create(name="Concurrent")
        self.food = Food.objects.create(name="Flour", category=category)
        self.meal = Meal.objects.create(name="Concurrent bread")
        MealIngredient.objects.create(
            meal=self.meal,
            food=self.food,
            quantity=Decimal("100"),
            unit="g",
        )
        self.schedule = schedule_meal(
            self.user,
            self.meal,
            date.today(),
            MealSchedule.MealType.BREAKFAST,
        )
        self.pantry = PantryItem.objects.create(
            user=self.user,
            food=self.food,
            quantity=Decimal("500"),
            unit="g",
        )

    def test_concurrent_requests_consume_one_schedule_only_once(self):
        barrier = Barrier(2)

        def cook():
            close_old_connections()
            try:
                barrier.wait()
                mark_scheduled_meal_cooked(self.user, self.schedule.pk)
                return "cooked", None
            except ValueError as error:
                return "rejected", str(error)
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _index: cook(), range(2)))

        self.assertEqual(
            sorted(result[0] for result in results),
            ["cooked", "rejected"],
            msg=f"Concurrent cooking outcomes: {results}",
        )
        rejected_message = next(message for result, message in results if result == "rejected")
        self.assertIn("already been cooked", rejected_message)
        self.assertEqual(MealConsumption.objects.filter(schedule=self.schedule).count(), 1)
        self.pantry.refresh_from_db()
        self.assertEqual(self.pantry.quantity, Decimal("400.00"))


class MealCookingMigrationTests(TransactionTestCase):
    def test_existing_scheduled_meals_survive_cooking_migration(self):
        user_model = get_user_model()
        user = user_model.objects.create_user(
            username="migration-cook",
            email="migration-cook@example.com",
            password="test-password",
        )
        category = FoodCategory.objects.create(name="Migration")
        Food.objects.create(name="Oats", category=category)
        meal = Meal.objects.create(name="Oat porridge")
        schedule = MealSchedule.objects.create(
            user=user,
            meal=meal,
            date=date.today(),
            meal_type=MealSchedule.MealType.BREAKFAST,
            servings=3,
        )

        latest = ("meals", "0008_alter_mealingredient_quantity")
        try:
            MigrationExecutor(connection).migrate([("meals", "0006_alter_mealingredient_quantity_and_more")])
            MigrationExecutor(connection).migrate([latest])

            preserved = MealSchedule.objects.get(pk=schedule.pk)
            self.assertEqual(preserved.meal_id, meal.pk)
            self.assertEqual(preserved.servings, 3)
            self.assertFalse(preserved.is_cooked)
            self.assertIsNone(preserved.cooked_at)
        finally:
            MigrationExecutor(connection).migrate([latest])
