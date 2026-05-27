from django.db import models
from django.utils.timezone import now


class SeasonManager(models.Manager):

    def create_season(self, nom, dataInici, dataFi):
        return self.create(nom=nom, dataInici=dataInici, dataFi=dataFi)

    def iniciar(self, temporada):
        from django.db import transaction
        from .models import EstatTemporada
        from apps.leagues.services import generar_snapshots_temporada

        if temporada.estat != EstatTemporada.PENDENT:
            raise ValueError(
                f"No es pot iniciar una temporada en estat '{temporada.estat}'. "
                "Només es poden iniciar temporades en estat PENDENT."
            )

        with transaction.atomic():
            temporades_actives = (
                self.select_for_update()
                .filter(estat=EstatTemporada.ACTIVA)
                .exclude(pk=temporada.pk)
            )

            for activa in temporades_actives:
                # Abans de tancar automàticament l'anterior, consolidem el seu històric.
                generar_snapshots_temporada(activa)
                activa.estat = EstatTemporada.TANCADA
                activa.save(update_fields=["estat"])

            temporada.estat = EstatTemporada.ACTIVA
            temporada.save(update_fields=["estat"])

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
