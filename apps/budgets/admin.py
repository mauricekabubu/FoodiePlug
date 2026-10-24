from django.contrib import admin
from .models import Budget, BudgetEntry

# Register your models here.
admin.site.register(Budget)
admin.site.register(BudgetEntry)
