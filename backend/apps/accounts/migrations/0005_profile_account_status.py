from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_alter_profile_estatvalidacioadmin'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='account_status',
            field=models.CharField(
                choices=[
                    ('active', 'Actiu'),
                    ('blocked', 'Bloquejat'),
                    ('suspended', 'Suspès'),
                ],
                default='active',
                db_index=True,
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='profile',
            name='suspension_reason',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='suspended_until',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text='Null indica suspensió indefinida. Ignorat si account_status != suspended.',
            ),
        ),
    ]
