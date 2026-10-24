from django.contrib import admin
from .models import ShoppingItem, ShoppingList

# Register your models here.
admin.site.register(ShoppingList)
admin.site.register(ShoppingItem)
