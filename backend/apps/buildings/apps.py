from django.apps import AppConfig

class BuildingsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.buildings'

    def ready(self):
        import apps.buildings.signals # Aixo enregistra els senyals quan l'aplicació està llesta.