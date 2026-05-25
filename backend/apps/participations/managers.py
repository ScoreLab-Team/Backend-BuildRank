from django.db import models
from django.db.models import Sum
from apps.buildings.models import EstatValidacio

class ParticipationManager(models.Manager):

    def create_participation(self, edifici, lliga):
        """Crea una participació amb la puntuació efectiva de l'edifici.

        Prioritat:
        1. puntuacioBase, si existeix.
        2. puntuacioBaseOpenData, per edificis provinents de CEE/Open Data.
        3. 0 si encara no hi ha dades suficients.

        No sumem aquí les millores validades perquè la consolidació de millores
        es fa explícitament a l'inici de temporada actualitzant puntuacioBase.
        Això evita dobles comptatges.
        """
        if edifici.puntuacioBase is not None:
            puntuacio_inicial = edifici.puntuacioBase
        elif edifici.puntuacioBaseOpenData is not None:
            puntuacio_inicial = edifici.puntuacioBaseOpenData
        else:
            puntuacio_inicial = 0

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