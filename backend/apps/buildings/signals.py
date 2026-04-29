# apps/buildings/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Habitatge, DadesEnergetiques
from .scoring import calcular_building_health_score, calcular_classificacio_estimada
from apps.buildings.services.segmentator import BuildingSegmentator


def _recalcular_edifici(edifici):
    """Recalcula el BHS i la classificació energètica d'un edifici."""
    if not edifici:
        return

    update_fields = []

    scores = []
    habitatges = edifici.habitatges.select_related("dadesEnergetiques").all()

    for habitatge in habitatges:
        dades = getattr(habitatge, "dadesEnergetiques", None)

        if dades is None:
            continue

        score_data = calcular_building_health_score(dades)
        scores.append(score_data["score"])

    if scores:
        puntuacio = sum(scores) / len(scores)

        edifici.bhs_history.create(
            score=puntuacio,
            version="1.0",
            pesos={},
        )

        edifici.puntuacioBase = puntuacio
        update_fields.append("puntuacioBase")

    resultat = calcular_classificacio_estimada(edifici)

    edifici.classificacioEstimada = resultat["classificacio"]
    edifici.classificacioFont = resultat["font"]

    update_fields.extend([
        "classificacioEstimada",
        "classificacioFont",
    ])

    if edifici.localitzacio:
        group = BuildingSegmentator.assign_group(edifici)

        if edifici.grupComparable != group:
            edifici.grupComparable = group
            update_fields.append("grupComparable")

    edifici.save(update_fields=update_fields)


@receiver(post_save, sender=Habitatge)
@receiver(post_delete, sender=Habitatge)
def signal_habitatge(sender, instance, **kwargs):
    _recalcular_edifici(instance.edifici)


@receiver(post_save, sender=DadesEnergetiques)
@receiver(post_delete, sender=DadesEnergetiques)
def signal_dades_energetiques(sender, instance, **kwargs):
    try:
        habitatge = instance.dades_energetiques
    except Habitatge.DoesNotExist:
        return

    _recalcular_edifici(habitatge.edifici)