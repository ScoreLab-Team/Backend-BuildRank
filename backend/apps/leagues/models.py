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
    categoria = models.CharField(max_length=20, choices=CategoriaRanking.choices)
    divisio = models.CharField(max_length=10, choices=DivisioLliga.choices)

    temporada = models.ForeignKey(
        Temporada,
        on_delete=models.CASCADE,
        related_name="temporades"
    )

    objects = LeagueManager()

    def __str__(self):
        return self.nom

class RankingHistorico(models.Model):
    edifici = models.ForeignKey(
        "buildings.Edifici",
        on_delete=models.CASCADE,
        related_name="ranking_historic"
    )
    temporada = models.ForeignKey(
        Temporada,
        on_delete=models.CASCADE,
        related_name="ranking_historic"
    )
    categoria = models.CharField(
        max_length=20,
        choices=CategoriaRanking.choices
    )
    puntuacio = models.FloatField()
    posicio = models.IntegerField()
    divisio = models.CharField(max_length=50, blank=True)
    dataCalcul = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("edifici", "temporada", "categoria")
        ordering = ["temporada__dataInici", "categoria", "posicio"]

    def __str__(self):
        return f"{self.edifici} - {self.temporada} - {self.categoria}"