from django.db import models
from django.db.models import Sum
from apps.buildings.models import EstatValidacio

class ParticipationManager(models.Manager):

    def create_participation(self, edifici, lliga):
        puntuacio_base = edifici.puntuacioBase or 0

        puntuacio_millores = (
                edifici.implementacions.filter(
                    estatValidacio=EstatValidacio.VALIDADA
                ).aggregate(
                    total=Sum("millora__impactePunts")
                )["total"] or 0
        )

        puntuacio_inicial = puntuacio_base + puntuacio_millores

        return self.create(
            edifici=edifici,
            lliga=lliga,
            puntuacio=puntuacio_inicial,
            puntuacio_inicial=puntuacio_inicial,
            posicio=0,
            divisio=lliga.divisio
        )

    def update_score(self, participacio, new_score):
        participacio.puntuacio = new_score
        participacio.save()

    def get_segment_ranking(self, lliga, group):
        return self.filter(
            lliga=lliga,
            edifici__grupComparable=group
        ).order_by("-puntuacio")