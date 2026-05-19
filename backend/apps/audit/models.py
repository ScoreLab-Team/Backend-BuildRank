from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
    )
    method = models.CharField(max_length=10)
    endpoint = models.CharField(max_length=500)
    resource_type = models.CharField(max_length=100, blank=True)
    resource_id = models.CharField(max_length=100, blank=True)
    status_code = models.PositiveSmallIntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    duration_ms = models.PositiveIntegerField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['endpoint', '-timestamp']),
            models.Index(fields=['method', 'status_code']),
        ]

    def __str__(self):
        user_str = self.user.email if self.user else 'anon'
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] {user_str} {self.method} {self.endpoint} → {self.status_code}"
