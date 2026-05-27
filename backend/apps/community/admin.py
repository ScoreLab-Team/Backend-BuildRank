from django.contrib import admin
from .models import Votacio, OpcioVot, Vot


class OpcioVotInline(admin.TabularInline):
    model = OpcioVot
    extra = 2


class VotInline(admin.TabularInline):
    model = Vot
    readonly_fields = ('usuari', 'opcio', 'dataEmissio')
    extra = 0
    can_delete = False


@admin.register(Votacio)
class VotacioAdmin(admin.ModelAdmin):
    list_display = ('titol', 'edifici', 'estat', 'dataCreacio', 'dataLimit')
    list_filter = ('estat',)
    search_fields = ('titol', 'edifici__localitzacio__carrer')
    inlines = [OpcioVotInline, VotInline]


@admin.register(Vot)
class VotAdmin(admin.ModelAdmin):
    list_display = ('usuari', 'votacio', 'opcio', 'dataEmissio')
    readonly_fields = ('usuari', 'votacio', 'opcio', 'dataEmissio')
