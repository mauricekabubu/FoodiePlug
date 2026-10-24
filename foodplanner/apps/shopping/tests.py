from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.foods.models import Food, FoodCategory
from .models import ShoppingItem, ShoppingList


class ShoppingItemPaginationTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="shopping-reader",
            email="shopping-reader@example.com",
            password="safe-test-password",
        )
        self.other_user = user_model.objects.create_user(
            username="other-shopping-reader",
            email="other-shopping-reader@example.com",
            password="safe-test-password",
        )
        self.client.force_login(self.user)
        category = FoodCategory.objects.create(name="Shopping pagination")
        self.shopping_list = ShoppingList.objects.create(
            user=self.user,
            name="Large shopping list",
        )
        for number in range(22):
            food = Food.objects.create(
                name=f"Shopping detail food {number:02}",
                category=category,
            )
            ShoppingItem.objects.create(
                shopping_list=self.shopping_list,
                food=food,
                quantity=1,
                unit="piece",
            )
        self.purchased_food = Food.objects.get(name="Shopping detail food 00")
        ShoppingItem.objects.filter(
            shopping_list=self.shopping_list,
            food=self.purchased_food,
        ).update(is_purchased=True)
        self.other_list = ShoppingList.objects.create(
            user=self.other_user,
            name="Private shopping list",
        )

    def test_items_are_paginated_with_search_and_filters_preserved(self):
        response = self.client.get(
            reverse("shopping_list_detail", args=[self.shopping_list.pk]),
            {
                "q": "Shopping detail food",
                "status": "todo",
                "group": "category",
                "page": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["page_obj"].number, 2)
        self.assertEqual(response.context["item_total_count"], 22)
        self.assertEqual(response.context["item_result_count"], 21)
        self.assertEqual(len(response.context["items"]), 1)
        self.assertIn("q=Shopping+detail+food", response.context["page_query"])
        self.assertIn("status=todo", response.context["page_query"])
        self.assertIn("group=category", response.context["page_query"])

    def test_status_filter_and_list_ownership_are_enforced(self):
        purchased = self.client.get(
            reverse("shopping_list_detail", args=[self.shopping_list.pk]),
            {"status": "done"},
        )
        self.assertEqual(purchased.context["item_result_count"], 1)
        self.assertEqual(purchased.context["items"][0].food, self.purchased_food)

        private = self.client.get(
            reverse("shopping_list_detail", args=[self.other_list.pk])
        )
        self.assertEqual(private.status_code, 302)
