from django.db import models
from .managers import SeasonManager

class Temporada(models.Model):
    id_temporada = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=100)
    dataInici = models.DateField()
    dataFi = models.DateField()
    activa = models.BooleanField(default=False)

    objects = SeasonManager()

    def __str__(self):
        return f"{self.nom} ({self.id_temporada})"