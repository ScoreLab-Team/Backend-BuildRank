# apps/seasons/apps.py
from django.apps import AppConfig


class SeasonsConfig(AppConfig):
    name = 'apps.seasons'

    def ready(self):
        import apps.seasons.signals  # noqa