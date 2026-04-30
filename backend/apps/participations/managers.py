from django.db import models


class ParticipationManager(models.Manager):

    def create_participation(self, edifici, lliga):
        return self.create(
            edifici=edifici,
            lliga=lliga,
            puntuacio=0,
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