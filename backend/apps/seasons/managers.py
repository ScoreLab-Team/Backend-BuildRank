from django.db import models
from django.utils.timezone import now


class SeasonManager(models.Manager):

    def create_season(self, id_temporada, nom, dataInici, dataFi):
        return self.create(
            id_temporada=id_temporada,
            nom=nom,
            dataInici=dataInici,
            dataFi=dataFi,
            activa=False
        )

    def activate(self, temporada):
        self.filter(activa=True).update(activa=False)
        temporada.activa = True
        temporada.save()

    def deactivate(self, temporada):
        temporada.activa = False
        temporada.save()

    def is_active(self, temporada):
        today = now().date()
        return temporada.dataInici <= today <= temporada.dataFi and temporada.activa