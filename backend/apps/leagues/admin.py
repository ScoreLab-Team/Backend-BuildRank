from django.contrib import admin

from .models import Lliga


@admin.register(Lliga)
class LligaAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "nom",
        "categoria",
        "divisio",
        "temporada",
    )

    list_filter = (
        "categoria",
        "divisio",
        "temporada",
    )

    search_fields = (
        "nom",
    )

    autocomplete_fields = (
        "temporada",
    )