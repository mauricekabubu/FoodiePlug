from django.urls import path
from . import views

app_name = "budgets"

urlpatterns = [
    path("", views.budget_dashboard, name="dashboard"),
    path("create/", views.create_budget_view, name="create"),
    path("<int:budget_id>/", views.budget_detail, name="detail"),
    path("<int:budget_id>/edit/", views.edit_budget_view, name="edit"),
    path("<int:budget_id>/delete/", views.delete_budget_view, name="delete"),
    path("<int:budget_id>/expenses/add/", views.add_expense_view, name="add_expense"),
    path("<int:budget_id>/expenses/<int:expense_id>/edit/",views.edit_expense_view, name="edit_expense", ),
    path("<int:budget_id>/expenses/<int:expense_id>/delete/", views.delete_expense_view, name="delete_expense",),
    path("current/", views.current_budget, name="current"),
]