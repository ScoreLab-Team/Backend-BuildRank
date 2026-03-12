# apps/buildings/admin.py

from django.contrib import admin
from .models import Edifici, Habitatge, DadesEnergetiques, Localitzacio

admin.site.register(Edifici)
admin.site.register(Habitatge)
admin.site.register(DadesEnergetiques)
admin.site.register(Localitzacio)