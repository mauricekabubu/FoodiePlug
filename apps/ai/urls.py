from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("", views.ai_page, name="page"),
    path("chat/", views.chat, name="chat"),
    path(
        "conversations/<str:conversation_id>/",
        views.conversation_detail,
        name="conversation_detail",
    ),
    path(
        "actions/confirm/",
        views.confirm_pending_action,
        name="confirm_action",
    ),
]
