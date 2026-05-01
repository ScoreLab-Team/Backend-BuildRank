from django.db import models
from .managers import SeasonManager


class EstatTemporada(models.TextChoices):
    PENDENT = 'PENDENT', 'Pendent'
    ACTIVA = 'ACTIVA', 'Activa'
    TANCADA = 'TANCADA', 'Tancada'


class Temporada(models.Model):
    id_temporada = models.AutoField(primary_key=True)
    nom = models.CharField(max_length=100)
    dataInici = models.DateField()
    dataFi = models.DateField()
    estat = models.CharField(
        max_length=10,
        choices=EstatTemporada.choices,
        default=EstatTemporada.PENDENT,
    )

    objects = SeasonManager()

    @property
    def activa(self):
        return self.estat == EstatTemporada.ACTIVA

    def __str__(self):
        return f"{self.nom} ({self.id_temporada})"
