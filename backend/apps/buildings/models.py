# apps/buildings/models.py
from django.db import models

class Localitzacio(models.Model):
    carrer = models.CharField(max_length=100)
    numero = models.IntegerField()
    codi_postal = models.CharField(max_length=10)
    barri = models.CharField(max_length=100)
    latitud = models.FloatField()
    longitud = models.FloatField()
    zona_climatica = models.CharField(max_length=50)
    
    def __str__(self):
        return f"{self.carrer} {self.numero}, {self.codi_postal}"

class Edifici(models.Model):
    TIPOLGIA_CHOICES = [
        ("Residencial", "Residencial"),
        ("Comercial", "Comercial"),
        ("Mixt", "Mixt"),
    ]

    id_edifici = models.CharField(max_length=50, primary_key=True)
    any_construccio = models.IntegerField()
    tipologia = models.CharField(max_length=20, choices=TIPOLGIA_CHOICES)
    superficie_total = models.FloatField()
    reglament = models.CharField(max_length=100)
    orientacio_principal = models.CharField(max_length=50)
    puntuacio_base = models.FloatField()
    
    localitzacio = models.ForeignKey(Localitzacio, null=True, blank=True, on_delete=models.SET_NULL)
    
    def __str__(self):
        return f"Edifici {self.id_edifici}"

class Habitatge(models.Model):
    edifici = models.ForeignKey(Edifici, related_name="habitatges", on_delete=models.CASCADE)
    referencia_cadastral = models.CharField(max_length=50)
    planta = models.CharField(max_length=10)
    porta = models.CharField(max_length=10)
    superficie = models.FloatField()
    any_reforma = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.planta}{self.porta} - {self.referencia_cadastral}"

class DadesEnergetiques(models.Model):
    habitatge = models.OneToOneField(Habitatge, related_name="dades_energetiques", on_delete=models.CASCADE)
    qualificacio_global = models.CharField(max_length=2)
    consum_energia_primaria = models.FloatField()
    consum_energia_final = models.FloatField()
    emissions_co2 = models.FloatField()
    cost_anual_energia = models.FloatField()
    energia_calefaccio = models.FloatField(default=0)
    energia_refrigeracio = models.FloatField(default=0)
    energia_acs = models.FloatField(default=0)
    energia_enllumenament = models.FloatField(default=0)

    def __str__(self):
        return f"DadesEnergetiques {self.habitatge}"