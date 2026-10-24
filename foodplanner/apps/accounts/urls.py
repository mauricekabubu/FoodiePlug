from django.urls import path  # pyright: ignore[reportMissingImports]
from django.urls import reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from .password_reset import FoodiePlugPasswordResetForm, SafePasswordResetView

urlpatterns = [
    path('',views.intro, name='intro'),
    path('login/', views.login_user, name='login'),
    path('register/', views.register, name='register'),
    path('terms/', views.terms, name='terms'),
    path('privacy/', views.privacy, name='privacy'),
    path('contact/', views.contact, name='contact'),
    path('help/', views.help, name='help'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path(
        'dashboard/gemini-reminder/dismiss/',
        views.dismiss_gemini_key_reminder,
        name='gemini_reminder_dismiss',
    ),
    path(
        'forgot_password/',
        SafePasswordResetView.as_view(
            form_class=FoodiePlugPasswordResetForm,
            template_name='forgot-password.html',
            email_template_name='registration/password_reset_email.txt',
            html_email_template_name='registration/password_reset_email.html',
            subject_template_name='registration/password_reset_subject.txt',
            success_url=reverse_lazy('password_reset_done'),
        ),
        name='forgot_password',
    ),
    path(
        'password_reset/done/',
        auth_views.PasswordResetDoneView.as_view(
            template_name='password_reset_done.html',
        ),
        name='password_reset_done',
    ),
    path(
        'reset/<uidb64>/<token>/',
        auth_views.PasswordResetConfirmView.as_view(
            template_name='password_reset_confirm.html',
            success_url=reverse_lazy('password_reset_complete'),
        ),
        name='password_reset_confirm',
    ),
    path(
        'reset/done/',
        auth_views.PasswordResetCompleteView.as_view(
            template_name='password_reset_complete.html',
        ),
        name='password_reset_complete',
    ),
    path('profile/', views.profile, name='profile'),
    path('logout/', views.logout_user, name='logout'),
    path('settings/', views.settings, name='settings'),
]
