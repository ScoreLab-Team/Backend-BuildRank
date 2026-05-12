from django.contrib import admin

from .models import Participacio


@admin.register(Participacio)
class ParticipacioAdmin(admin.ModelAdmin):
    list_display = (
        "edifici",
        "lliga",
        "puntuacio",
        "posicio",
        "divisio",
    )

    list_filter = (
        "divisio",
        "lliga",
    )

    search_fields = (
        "edifici__localitzacio__carrer",
    )

    autocomplete_fields = (
        "edifici",
        "lliga",
    )

    ordering = ("-puntuacio",)