from django.db import models
import uuid
from django.utils import timezone
import datetime

# Create your models here.


class ParsedDataCache(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    data = models.JSONField(help_text="JSON serialized ParsedRequirementData")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = "Parsed Data Cache"
        verbose_name_plural = "Parsed Data Caches"

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + datetime.timedelta(minutes=10)
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)


class UserAiSettings(models.Model):
    user = models.OneToOneField(
        'auth.User', on_delete=models.CASCADE, related_name='ai_settings')
    ai_provider = models.CharField(max_length=32, default='openai')
    openai_model = models.CharField(max_length=64, blank=True, null=True)
    gemini_model = models.CharField(max_length=64, blank=True, null=True)
    openai_api_key = models.CharField(max_length=128, blank=True, null=True)
    gemini_api_key = models.CharField(max_length=128, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI設定({self.user.username})"
