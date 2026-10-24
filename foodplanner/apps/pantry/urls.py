from django.urls import path

from . import views


app_name = "pantry"


urlpatterns = [
    # Pantry dashboard
    path("",views.pantry,        name="pantry"
    ),

    # Add
    path(
        "add/",
        views.add_pantry_item,
        name="add"
    ),

    # Detail
    path(
        "<int:item_id>/",
        views.pantry_item_detail,
        name="detail"
    ),

    # Full edit
    path(
        "<int:item_id>/update/",
        views.update_pantry_item_view,
        name="update"
    ),

    # Quantity
    path(
        "<int:item_id>/quantity/",
        views.update_pantry_quantity,
        name="update_quantity"
    ),

    # Consume
    path(
        "<int:item_id>/consume/",
        views.consume_pantry_item,
        name="consume"
    ),

    # Remove
    path(
        "<int:item_id>/remove/",
        views.remove_pantry_item,
        name="remove"
    ),

    # Expiry
    path(
        "expiring/",
        views.expiring_items,
        name="expiring"
    ),

    path(
        "expired/",
        views.expired_items,
        name="expired"
    ),
]