from django.urls import path  # pyright: ignore[reportMissingImports]
from . import views

urlpatterns = [
    path('',views.intro, name='intro'),
    path('login/', views.login_user, name='login'),
    path('register/', views.register, name='register'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help, name='help'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('forgot_password/', views.forgot_password, name='forgot_password'),
    path('profile/', views.profile, name='profile'),
    path('logout/', views.logout_user, name='logout'),
    path('settings/', views.settings, name='settings'),
]
