import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ModerationLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("moderator_role", models.CharField(blank=True, max_length=20)),
                ("target_message_id", models.CharField(blank=True, max_length=255)),
                ("channel_id", models.CharField(blank=True, max_length=255)),
                ("action", models.CharField(
                    choices=[
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
                    ],
                    max_length=30,
                )),
                ("reason", models.TextField(blank=True)),
                ("previous_state", models.CharField(blank=True, max_length=30)),
                ("new_state", models.CharField(blank=True, max_length=30)),
                ("timestamp", models.DateTimeField(auto_now_add=True)),
                ("moderator", models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="moderation_actions",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("target_user", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="moderation_received",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "ordering": ["-timestamp"],
            },
        ),
        migrations.AddIndex(
            model_name="moderationlog",
            index=models.Index(fields=["moderator", "-timestamp"], name="chat_modera_moderat_idx"),
        ),
        migrations.AddIndex(
            model_name="moderationlog",
            index=models.Index(fields=["target_user", "-timestamp"], name="chat_modera_target__idx"),
        ),
        migrations.AddIndex(
            model_name="moderationlog",
            index=models.Index(fields=["channel_id", "-timestamp"], name="chat_modera_channel_idx"),
        ),
        migrations.AddIndex(
            model_name="moderationlog",
            index=models.Index(fields=["action", "-timestamp"], name="chat_modera_action__idx"),
        ),
    ]
