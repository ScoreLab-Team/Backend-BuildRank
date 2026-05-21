from django.db import models
from django.utils.timezone import now


class SeasonManager(models.Manager):

    def create_season(self, nom, dataInici, dataFi):
        return self.create(nom=nom, dataInici=dataInici, dataFi=dataFi)

    def iniciar(self, temporada):
        from .models import EstatTemporada
        if temporada.estat != EstatTemporada.PENDENT:
            raise ValueError(
                f"No es pot iniciar una temporada en estat '{temporada.estat}'. "
                "Només es poden iniciar temporades en estat PENDENT."
            )
        if self.filter(estat=EstatTemporada.ACTIVA).exists():
            raise ValueError("Ja existeix una temporada activa. Tanca-la primer.")
        temporada.estat = EstatTemporada.ACTIVA
        temporada.save()

    def tancar(self, temporada):
        from .models import EstatTemporada
        from apps.leagues.services import generar_snapshots_temporada

        if temporada.estat != EstatTemporada.ACTIVA:
            raise ValueError(
                f"No es pot tancar una temporada en estat '{temporada.estat}'. "
                "Només es poden tancar temporades en estat ACTIVA."
            )

        # Consolidar RankingHistorico abans de tancar la temporada.
        # Per decisió de producte només es consolida la categoria PROGRES.
        generar_snapshots_temporada(temporada)

        temporada.estat = EstatTemporada.TANCADA
        temporada.save()

    def is_active(self, temporada):
        from .models import EstatTemporada
        today = now().date()
        return (
            temporada.estat == EstatTemporada.ACTIVA
            and temporada.dataInici <= today <= temporada.dataFi
        )
