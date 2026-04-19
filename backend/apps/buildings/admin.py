# apps/buildings/admin.py

from django.utils import timezone

from django.contrib import admin
from .models import Edifici, EdificiAuditLog, Habitatge, DadesEnergetiques, Localitzacio


# ---------------------------------------------------------------------------
# Edifici
# ---------------------------------------------------------------------------
 
@admin.register(Edifici)
class EdificiAdmin(admin.ModelAdmin):
    list_display  = [
        'idEdifici', 'tipologia', 'anyConstruccio',
        'superficieTotal', 'puntuacioBase', 'actiu', 'dataDesactivacio',
    ]
    list_filter   = ['actiu', 'tipologia', 'orientacioPrincipal']
    search_fields = ['idEdifici', 'localitzacio__carrer', 'localitzacio__codiPostal']
    readonly_fields = ['puntuacioBase', 'dataDesactivacio', 'motivDesactivacio']
    actions = ['desactivar_edificis', 'reactivar_edificis']
 
    @admin.action(description='Desactivar edificis seleccionats')
    def desactivar_edificis(self, request, queryset):
        ara = timezone.now()
        actualitzats = 0
        for edifici in queryset.filter(actiu=True):
            edifici.actiu = False
            edifici.dataDesactivacio = ara
            edifici.motivDesactivacio = 'Desactivació massiva des del panell admin'
            edifici.save(update_fields=['actiu', 'dataDesactivacio', 'motivDesactivacio'])
 
            EdificiAuditLog.objects.create(
                edifici=edifici,
                edifici_id_snapshot=edifici.idEdifici,
                accio='DESACTIVAR',
                usuari=request.user,
                camps_modificats={"actiu": [True, False]},
                motiu='Desactivació massiva des del panell admin',
                ip=request.META.get('REMOTE_ADDR'),
            )
            actualitzats += 1
 
        self.message_user(request, f"{actualitzats} edifici(s) desactivat(s).")
 
    @admin.action(description='Reactivar edificis seleccionats')
    def reactivar_edificis(self, request, queryset):
        actualitzats = 0
        for edifici in queryset.filter(actiu=False):
            edifici.actiu = True
            edifici.dataDesactivacio = None
            edifici.motivDesactivacio = ''
            edifici.save(update_fields=['actiu', 'dataDesactivacio', 'motivDesactivacio'])
 
            EdificiAuditLog.objects.create(
                edifici=edifici,
                edifici_id_snapshot=edifici.idEdifici,
                accio='REACTIVAR',
                usuari=request.user,
                camps_modificats={"actiu": [False, True]},
                motiu='Reactivació des del panell admin',
                ip=request.META.get('REMOTE_ADDR'),
            )
            actualitzats += 1
 
        self.message_user(request, f"{actualitzats} edifici(s) reactivat(s).")
 
 
# ---------------------------------------------------------------------------
# EdificiAuditLog 
# ---------------------------------------------------------------------------
 
@admin.register(EdificiAuditLog)
class EdificiAuditLogAdmin(admin.ModelAdmin):
    list_display  = [
        'timestamp', 'accio', 'edifici_id_snapshot',
        'usuari', 'motiu', 'ip',
    ]
    list_filter   = ['accio']
    search_fields = ['edifici_id_snapshot', 'usuari__username', 'motiu']
    readonly_fields = [
        'edifici', 'edifici_id_snapshot', 'accio', 'usuari',
        'timestamp', 'camps_modificats', 'motiu', 'ip',
    ]
 
    # El log és immutable: no es pot crear ni esborrar des del panell
    def has_add_permission(self, request):
        return False
 
    def has_delete_permission(self, request, obj=None):
        return False
 
    def has_change_permission(self, request, obj=None):
        return False
 
 
# ---------------------------------------------------------------------------
# Registres simples (sense canvis)
# ---------------------------------------------------------------------------
 
admin.site.register(Habitatge)
admin.site.register(DadesEnergetiques)
admin.site.register(Localitzacio)
 
