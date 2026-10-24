from django.db import models

# Create your models here.
class FoodCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description =  models.TextField(null=True, blank=True)
    
    class Meta:
        verbose_name = "Food Category"
        verbose_name_plural = "Food Categories"
        ordering = ["name"]
        
    def __str__(self):
        return self.name


class Food(models.Model):
    class UnitChoices(models.TextChoices):
        KG = "kg","Kilogram"
        GRAM = "g","Gram"
        LITRE = "l","Litre"
        ML = "ml","Millilitre"
        PIECE = "piece","Piece"
        BUNCH = "bunch","Bunch"
        PACKET = "packet","Packet"
        
    name = models.CharField(max_length=150, unique=True)
    category = models.ForeignKey(FoodCategory, on_delete=models.PROTECT, db_index=False,
                                 related_name="foods")
    default_unit = models.CharField(max_length=20, choices=UnitChoices.choices,
                                    default=UnitChoices.PIECE)
    is_perishable = models.BooleanField(default=False)
    shelf_life = models.PositiveIntegerField(
        null=True, blank=True, help_text="Typical shelf life in days"
    )
    
    image = models.ImageField(
            upload_to="foods/",
            blank=True,
            null=True
        )
    
    is_active = models.BooleanField(default=True)    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_active", "name"], name="food_active_name_idx"),
            models.Index(
                fields=["category", "is_active", "name"],
                name="food_category_active_name_idx",
            ),
        ]
        
    def __str__(self):
        return self.name
    