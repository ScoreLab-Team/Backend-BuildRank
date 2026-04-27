# apps/buildings/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Habitatge, DadesEnergetiques
from .scoring import calcular_building_health_score, calcular_classificacio_estimada


def _recalcular_edifici(edificio):
    """Lògica compartida per recalcular BHS i classificació d'un edifici."""
    if not edificio:
        return

    scores = []
    for h in edificio.habitatges.all():
        if hasattr(h, "dadesEnergetiques") and h.dadesEnergetiques is not None:
            score_data = calcular_building_health_score(h.dadesEnergetiques)
            scores.append(score_data["score"])

    if scores:
        promedio = sum(scores) / len(scores)
        edificio.bhs_history.create(score=promedio, version="1.0", pesos={})
        edificio.puntuacioBase = promedio

    resultat = calcular_classificacio_estimada(edificio)
    edificio.classificacioEstimada = resultat["classificacio"]
    edificio.classificacioFont = resultat["font"]

    edificio.save(update_fields=[
        "puntuacioBase",
        "classificacioEstimada",
        "classificacioFont",
    ])


@receiver(post_save, sender=Habitatge)
@receiver(post_delete, sender=Habitatge)
def signal_habitatge(sender, instance, **kwargs):
    _recalcular_edifici(instance.edifici)


@receiver(post_save, sender=DadesEnergetiques)
@receiver(post_delete, sender=DadesEnergetiques)
def signal_dades_energetiques(sender, instance, **kwargs):
    # La relació és inversa: Habitatge → DadesEnergetiques
    try:
        habitatge = instance.dades_energetiques  # related_name del OneToOneField
    except Habitatge.DoesNotExist:
        return  # Creat des de l'admin sense habitatge → ignorem
    _recalcular_edifici(habitatge.edifici)