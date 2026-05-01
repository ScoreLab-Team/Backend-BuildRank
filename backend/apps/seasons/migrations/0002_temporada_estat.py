from django.db import migrations, models


def migrate_activa_to_estat(apps, schema_editor):
    Temporada = apps.get_model('seasons', 'Temporada')
    Temporada.objects.filter(activa=True).update(estat='ACTIVA')
    Temporada.objects.filter(activa=False).update(estat='PENDENT')


class Migration(migrations.Migration):

    dependencies = [
        ('seasons', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='temporada',
            name='estat',
            field=models.CharField(
                choices=[('PENDENT', 'Pendent'), ('ACTIVA', 'Activa'), ('TANCADA', 'Tancada')],
                default='PENDENT',
                max_length=10,
            ),
        ),
        migrations.RunPython(migrate_activa_to_estat, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='temporada',
            name='activa',
        ),
    ]
