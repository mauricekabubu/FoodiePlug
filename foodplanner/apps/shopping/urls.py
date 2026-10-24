from django.urls import path

from . import views


urlpatterns = [
    # ---------- Lists ----------
    path("lists/", views.shopping_lists, name="shopping_lists"),
    path("lists/create/", views.create_list, name="create_list"),
    path("lists/<int:list_id>/", views.shopping_list_detail, name="shopping_list_detail"),
    path("lists/<int:list_id>/rename/", views.rename_list, name="rename_list"),
    path("lists/<int:list_id>/delete/", views.delete_list, name="delete_list"),

    # ---------- Archive (soft delete; needs the is_archived field) ----------
    path("lists/<int:list_id>/archive/", views.archive_list, name="archive_list"),
    path("lists/<int:list_id>/restore/", views.restore_list, name="restore_list"),

    # ---------- Items ----------
    path("lists/<int:list_id>/items/add/", views.add_item, name="add_item"),
    path("items/<int:item_id>/update/", views.update_item, name="update_item"),
    path("items/<int:item_id>/remove/", views.remove_item, name="remove_item"),

    # ---------- Purchase state ----------
    path("items/<int:item_id>/purchase/", views.purchase_item, name="purchase_item"),
    path("items/<int:item_id>/unpurchase/", views.unpurchase_item, name="unpurchase_item"),
]