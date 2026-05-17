from __future__ import annotations

from typing import Dict, Optional

from django.db import transaction
from django.db.models import Sum

from apps.buildings.models import Edifici, EstatValidacio, MilloraImplementada
from .models import Temporada


SEASONAL_BHS_VERSION = "SEAS-1.0"


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _temporada_anterior(temporada: Temporada) -> Optional[Temporada]:
    return (
        Temporada.objects
        .filter(dataFi__lte=temporada.dataInici)
        .exclude(pk=temporada.pk)
        .order_by("-dataFi")
        .first()
    )


def _base_actual(edifici: Edifici) -> float:
    """
    Base de partida abans d'aplicar el tancament de la temporada anterior.

    Prioritat:
    1. puntuacioBase, si ja existeix.
    2. puntuacioBaseOpenData, si només hi ha dades CEE.
    3. 0 si no hi ha cap dada encara.
    """
    if edifici.puntuacioBase is not None:
        return float(edifici.puntuacioBase)

    if edifici.puntuacioBaseOpenData is not None:
        return float(edifici.puntuacioBaseOpenData)

    return 0.0


def _bonus_millores_validades(edifici: Edifici, temporada_anterior: Optional[Temporada]) -> float:
    """
    Només compten millores implementades i VALIDADA dins la temporada anterior.
    No es fa servir tota la història de l'edifici.
    """
    if temporada_anterior is None:
        return 0.0

    resultat = (
        MilloraImplementada.objects
        .filter(
            edifici=edifici,
            estatValidacio=EstatValidacio.VALIDADA,
            dataExecucio__gte=temporada_anterior.dataInici,
            dataExecucio__lte=temporada_anterior.dataFi,
        )
        .aggregate(total=Sum("millora__impactePunts"))
    )

    return float(resultat["total"] or 0.0)


def _actualitzar_participacions_temporada(temporada: Temporada, edifici: Edifici, puntuacio: float) -> int:
    """
    Si ja existeix la participació de l'edifici en la nova temporada, sincronitzem
    la seva puntuació inicial amb la nova puntuacioBase.
    """
    from apps.participations.models import Participacio

    return (
        Participacio.objects
        .filter(lliga__temporada=temporada, edifici=edifici)
        .update(puntuacio=puntuacio)
    )


def _recalcular_posicions_temporada(temporada: Temporada) -> int:
    """
    Reordena posicions dins de cada lliga després d'actualitzar puntuacions.
    """
    from apps.leagues.models import Lliga
    from apps.participations.models import Participacio

    actualitzades = 0

    for lliga in Lliga.objects.filter(temporada=temporada):
        participacions = (
            Participacio.objects
            .filter(lliga=lliga)
            .order_by("-puntuacio", "edifici_id")
        )

        for index, participacio in enumerate(participacions, start=1):
            if participacio.posicio != index:
                participacio.posicio = index
                participacio.save(update_fields=["posicio"])
                actualitzades += 1

    return actualitzades


def actualitzar_puntuacions_base_inici_temporada(temporada: Temporada) -> Dict[str, object]:
    """
    Recalcula la puntuacioBase quan comença una nova temporada.

    Regla de negoci:
    - Les simulacions no modifiquen puntuacioBase.
    - Validar una MilloraImplementada tampoc modifica immediatament puntuacioBase.
    - En iniciar una nova temporada, puntuacioBase = base actual + impacte de millores
      VALIDADA de la temporada anterior, limitat a 0-100.
    """
    temporada_anterior = _temporada_anterior(temporada)

    resum = {
        "temporada": temporada.id_temporada,
        "temporada_anterior": temporada_anterior.id_temporada if temporada_anterior else None,
        "edificis_processats": 0,
        "edificis_actualitzats": 0,
        "participacions_actualitzades": 0,
        "posicions_actualitzades": 0,
    }

    with transaction.atomic():
        edificis = Edifici.actius.select_for_update().all()

        for edifici in edificis:
            resum["edificis_processats"] += 1

            base = _base_actual(edifici)
            bonus = _bonus_millores_validades(edifici, temporada_anterior)
            nova_puntuacio = clamp(base + bonus)

            if edifici.puntuacioBase != nova_puntuacio:
                edifici.puntuacioBase = nova_puntuacio
                edifici.save(update_fields=["puntuacioBase"])
                resum["edificis_actualitzats"] += 1

            edifici.bhs_history.create(
                score=nova_puntuacio,
                version=SEASONAL_BHS_VERSION,
                pesos={
                    "criteri": "inici_temporada",
                    "base_anterior": round(base, 2),
                    "bonus_millores_validades_temporada_anterior": round(bonus, 2),
                    "temporada_anterior": temporada_anterior.id_temporada if temporada_anterior else None,
                    "nota": (
                        "La puntuacioBase només es recalcula a l'inici de temporada "
                        "i només incorpora millores implementades validades de la temporada anterior."
                    ),
                },
            )

            resum["participacions_actualitzades"] += _actualitzar_participacions_temporada(
                temporada,
                edifici,
                nova_puntuacio,
            )

        resum["posicions_actualitzades"] = _recalcular_posicions_temporada(temporada)

    return resum
