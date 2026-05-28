from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_profile_avatar"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="chat_stream_id_version",
            field=models.PositiveSmallIntegerField(default=1),
        ),
    ]
