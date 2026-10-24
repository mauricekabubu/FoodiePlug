from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Food, FoodCategory


class FoodLibraryPaginationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="food-reader",
            email="food-reader@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.user)
        category = FoodCategory.objects.create(name="Pagination produce")
        for number in range(27):
            Food.objects.create(
                name=f"Pagination food {number:02}",
                category=category,
            )

    def test_search_and_category_are_preserved_across_pages(self):
        response = self.client.get(
            reverse("foods:foods"),
            {"q": "Pagination food", "category": FoodCategory.objects.get().pk, "page": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["page_obj"].paginator.count, 27)
        self.assertIn("q=Pagination+food", response.context["page_query"])
        self.assertIn("category=", response.context["page_query"])
        self.assertEqual(len(response.context["foods"]), 3)

    def test_invalid_and_out_of_range_pages_use_valid_page_bounds(self):
        for requested_page, expected_page in (("invalid", 1), ("999", 2)):
            with self.subTest(page=requested_page):
                response = self.client.get(
                    reverse("foods:foods"),
                    {"page": requested_page},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["page_obj"].number, expected_page)
