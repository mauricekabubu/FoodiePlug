from django.contrib import admin
from .models import UserAIConfig, AIConversation, AIMessage

# Register your models here.
admin.site.register(UserAIConfig)
admin.site.register(AIMessage)
admin.site.register(AIConversation)