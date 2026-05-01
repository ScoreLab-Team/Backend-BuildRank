from django.db import models
from apps.leagues.models import Lliga
from apps.buildings.models import Edifici
from .managers import ParticipationManager

class Participacio(models.Model):
    edifici = models.ForeignKey(
        Edifici,
        on_delete=models.CASCADE,
        related_name="participations"
    )

    lliga = models.ForeignKey(
        Lliga,
        on_delete=models.CASCADE,
        related_name="participations"
    )

    puntuacio = models.FloatField()
    posicio = models.IntegerField()
    divisio = models.CharField(max_length=50)

    objects = ParticipationManager()

    class Meta:
        unique_together = ("edifici", "lliga")

    def __str__(self):
        return f"{self.edifici} - {self.lliga}"