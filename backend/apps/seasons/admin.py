from django.contrib import admin
from django.contrib import messages

from .models import Temporada, EstatTemporada


@admin.register(Temporada)
class TemporadaAdmin(admin.ModelAdmin):
    list_display = ('nom', 'dataInici', 'dataFi', 'estat')
    list_filter = ('estat',)
    search_fields = ('nom',)
    readonly_fields = ('estat',)
    ordering = ('-dataInici',)
    actions = ['action_iniciar', 'action_tancar']

    @admin.action(description='Iniciar temporades seleccionades')
    def action_iniciar(self, request, queryset):
        errors = []
        iniciades = 0
        for temporada in queryset:
            try:
                Temporada.objects.iniciar(temporada)
                iniciades += 1
            except ValueError as e:
                errors.append(f"'{temporada.nom}': {e}")
        if iniciades:
            self.message_user(
                request,
                f"{iniciades} temporada(es) iniciada(es) correctament.",
                messages.SUCCESS,
            )
        for err in errors:
            self.message_user(request, err, messages.ERROR)

    @admin.action(description='Tancar temporades seleccionades')
    def action_tancar(self, request, queryset):
        errors = []
        tancades = 0
        for temporada in queryset:
            try:
                Temporada.objects.tancar(temporada)
                tancades += 1
            except ValueError as e:
                errors.append(f"'{temporada.nom}': {e}")
        if tancades:
            self.message_user(
                request,
                f"{tancades} temporada(es) tancada(es) correctament.",
                messages.SUCCESS,
            )
        for err in errors:
            self.message_user(request, err, messages.ERROR)
