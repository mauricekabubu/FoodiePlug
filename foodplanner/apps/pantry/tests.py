from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.foods.models import Food, FoodCategory
from .models import PantryItem
from services.pantry import get_user_pantry


class PantryPaginationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="pantry-reader",
            email="pantry-reader@example.com",
            password="safe-test-password",
        )
        self.other_user = user_model.objects.create_user(
            username="other-pantry-reader",
            email="other-pantry-reader@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.user)
        category = FoodCategory.objects.create(name="Pantry pagination")
        for number in range(21):
            food = Food.objects.create(
                name=f"Pantry food {number:02}",
                category=category,
            )
            PantryItem.objects.create(
                user=self.user,
                food=food,
                quantity=Decimal("2"),
                minimum_quantity=Decimal("1"),
            )
        PantryItem.objects.create(
            user=self.other_user,
            food=Food.objects.get(name="Pantry food 00"),
            quantity=Decimal("2"),
            minimum_quantity=Decimal("1"),
        )

    def test_pantry_paginates_and_preserves_search_status_and_sort(self):
        response = self.client.get(
            reverse("pantry:pantry"),
            {
                "q": "Pantry food",
                "status": "available",
                "sort": "name",
                "page": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["pantry_count"], 21)
        self.assertEqual(response.context["result_count"], 21)
        self.assertEqual(len(response.context["pantry_items"]), 1)
        self.assertEqual(response.context["pantry_items"][0].food.name, "Pantry food 20")
        self.assertIn("q=Pantry+food", response.context["page_query"])
        self.assertIn("status=available", response.context["page_query"])
        self.assertIn("sort=name", response.context["page_query"])

    def test_invalid_pages_and_status_filter_are_safe_and_user_scoped(self):
        response = self.client.get(
            reverse("pantry:pantry"),
            {"status": "low", "page": "invalid"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 1)
        self.assertEqual(response.context["result_count"], 0)
        self.assertEqual(response.context["pantry_count"], 21)

    def test_food_and_category_rendering_uses_one_query(self):
        with self.assertNumQueries(1):
            pantry_items = list(get_user_pantry(self.user))
            rendered_categories = [
                item.food.category.name for item in pantry_items
            ]

        self.assertEqual(len(rendered_categories), 21)
