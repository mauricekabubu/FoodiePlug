from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    email = models.EmailField(unique=True)

    def __str__(self):
        return self.username


class Profile(models.Model):

    class LanguageChoices(models.TextChoices):
        ENGLISH = "english", "English"
        SWAHILI = "swahili", "Kiswahili"
        SHENG = "sheng", "Sheng"
        KENYAN_MIX = "kenyan_mix", "Kenyan Mix"

    class SlangLevels(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile"
    )

    display_name = models.CharField(
        max_length=200,
        blank=True
    )

    avatar = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True
    )

    preferred_language = models.CharField(
        max_length=20,
        choices=LanguageChoices.choices,
        default=LanguageChoices.KENYAN_MIX
    )

    slang_level = models.CharField(
        max_length=10,
        choices=SlangLevels.choices,
        default=SlangLevels.MEDIUM
    )

    timezone = models.CharField(
        max_length=50,
        default="Africa/Nairobi"
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f"{self.user.username}'s Profile"
    



class Message(models.Model):

    class TopicChoices(models.TextChoices):
        GENERAL_QUESTION = "general_question", "General question"
        FEEDBACK = "feedback", "Feedback"
        TECHNICAL_SUPPORT = "technical_support", "Technical support"
        ACCOUNT_ISSUE = "account_issue", "Account issue"
        FEATURE_REQUEST = "feature_request", "Feature request"
        PARTNERSHIP = "partnership", "Partnership"
        OTHER = "other", "Other"

    full_name = models.CharField(max_length=100)

    email = models.EmailField(max_length=254)

    topic = models.CharField(
        max_length=30,
        choices=TopicChoices.choices,
        default=TopicChoices.GENERAL_QUESTION,
    )

    message = models.TextField()

    username = models.CharField(
        max_length=150,
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.topic} — {self.email}"

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Contact message"
        verbose_name_plural = "Contact messages"


class PasswordResetAttempt(models.Model):
    key = models.CharField(max_length=64, primary_key=True)
    window_started_at = models.DateTimeField()
    attempt_count = models.PositiveSmallIntegerField(default=0)

    
    