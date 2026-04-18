# apps/buildings/admin.py

from django.contrib import admin
from .models import Edifici, Habitatge, DadesEnergetiques, Localitzacio

@admin.register(Edifici)
class EdificiAdmin(admin.ModelAdmin):
    list_display = ['idEdifici', 'tipologia', 'anyConstruccio', 'actiu', 'dataDesactivacio']
    list_filter = ['actiu', 'tipologia']
    readonly_fields = ['dataDesactivacio', 'motivDesactivacio', 'puntuacioBase']
    actions = ['desactivar_edificis', 'reactivar_edificis']

    @admin.action(description='Desactivar edificis seleccionats')
    def desactivar_edificis(self, request, queryset):
        from django.utils import timezone

        updated = queryset.filter(actiu=True).update(
            actiu=False,
            dataDesactivacio=timezone.now(),
            motivDesactivacio='Desactivació massiva des del panell admin'
        )
        self.message_user(request, f"{updated} edifici(s) desactivat(s).")

    @admin.action(description='Reactivar edificis seleccionats')
    def reactivar_edificis(self, request, queryset):
        updated = queryset.filter(actiu=False).update(
            actiu=True,
            dataDesactivacio=None,
            motivDesactivacio=''
        )
        self.message_user(request, f"{updated} edifici(s) reactivat(s).")
        
admin.site.register(Habitatge)
admin.site.register(DadesEnergetiques)
admin.site.register(Localitzacio)