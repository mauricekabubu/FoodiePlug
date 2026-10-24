from django.db import models
from django.conf import settings

from apps.foods.models import Food

# Create your models here.
class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL,
                             on_delete=models.CASCADE, db_index=False, related_name="budgets")
    name = models.CharField(max_length=150, default="Food Budget")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["-start_date"]
        indexes = [
            models.Index(
                fields=["user", "-start_date", "-id"],
                name="budget_user_start_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.amount}"
    
class BudgetEntry(models.Model):
    budget = models.ForeignKey(Budget, on_delete=models.CASCADE,
                               db_index=False, related_name="entries")
    food = models.ForeignKey(Food, on_delete=models.PROTECT, related_name="budget_entries",
                             null=True, blank=True)
    description = models.TextField(blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField()
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        
        ordering = ["-date", "-created_at", "-pk"]
        indexes = [
            models.Index(
                fields=["budget", "-date", "-created_at", "-id"],
                name="budgetentry_recent_idx",
            ),
        ]

    def __str__(self):
        return f"{self.description} - KES {self.amount}"
    
    
