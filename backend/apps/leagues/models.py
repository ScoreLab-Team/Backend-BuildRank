from django.db import models
from apps.seasons.models import Temporada
from .managers import LeagueManager

class CategoriaRanking(models.TextChoices):
    EFICIENCIA = "EFICIENCIA"
    RESILIENCIA = "RESILIENCIA"
    PROGRES = "PROGRES"


class DivisioLliga(models.TextChoices):
    BRONZE = "Bronze"
    SILVER = "Silver"
    GOLD = "Gold"


class Lliga(models.Model):
    nom = models.CharField(max_length=100)
    categoria = models.CharField(max_length=20, choices=CategoryRanking.choices)
    divisio = models.CharField(max_length=10, choices=DivisionLeague.choices)

    temporada = models.ForeignKey(
        Temporada,
        on_delete=models.CASCADE,
        related_name="temporades"
    )

    objects = LeagueManager()

    def __str__(self):
        return self.nom