from django.db import models

from apps.accounts.models import User


class ModerationLog(models.Model):
    ACTION_CHOICES = [
        ("flag_message", "Reportar missatge"),
        ("hide_message", "Ocultar missatge"),
        ("delete_message", "Eliminar missatge"),
        ("restore_message", "Restaurar missatge"),
        ("dismiss_flag", "Desestimar report"),
        ("warn_user", "Advertir usuari"),
        ("mute_user", "Silenciar usuari"),
        ("unmute_user", "Dessilenciar usuari"),
        ("ban_from_channel", "Expulsar del canal"),
        ("unban_from_channel", "Readmetre al canal"),
        ("global_ban", "Expulsió global"),
        ("global_unban", "Aixecar expulsió global"),
        ("shadow_ban", "Shadow ban"),
        ("shadow_unban", "Aixecar shadow ban"),
    ]

    moderator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="moderation_actions"
    )
    moderator_role = models.CharField(max_length=20, blank=True)
    target_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="moderation_received"
    )
    target_message_id = models.CharField(max_length=255, blank=True)
    channel_id = models.CharField(max_length=255, blank=True)
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    reason = models.TextField(blank=True)
    previous_state = models.CharField(max_length=30, blank=True)
    new_state = models.CharField(max_length=30, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["moderator", "-timestamp"]),
            models.Index(fields=["target_user", "-timestamp"]),
            models.Index(fields=["channel_id", "-timestamp"]),
            models.Index(fields=["action", "-timestamp"]),
        ]

    def __str__(self):
        return f"[{self.timestamp}] {self.moderator_role} → {self.action} ({self.channel_id})"
