from django.contrib import admin
from .models import User, Profile, Message

# Register your models here.

admin.site.register(User)
admin.site.register(Profile)
admin.site.register(Message)
