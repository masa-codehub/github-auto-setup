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
