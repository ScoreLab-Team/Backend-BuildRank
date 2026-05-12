# apps/buildings/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Habitatge, DadesEnergetiques, DadesEnergetiquesOpenData
from .scoring import calcular_building_health_score, calcular_classificacio_estimada, calcular_bhs_opendata


def _recalcular_edifici(edifici):
    """Recalcula el BHS i la classificació energètica d'un edifici."""
    if not edifici:
        return

    update_fields = []

    # --- BHS d'habitatges (usuaris) ---
    scores = []
    score_data_referencia = None
    habitatges = edifici.habitatges.select_related("dadesEnergetiques").all()

    for habitatge in habitatges:
        dades = getattr(habitatge, "dadesEnergetiques", None)
        if dades is None:
            continue
        score_data = calcular_building_health_score(dades)
        scores.append(score_data["score"])
        score_data_referencia = score_data

    if scores:
        puntuacio = sum(scores) / len(scores)
        edifici.bhs_history.create(
            score=puntuacio,
            version=score_data_referencia.get("version", "1.0") if score_data_referencia else "1.0",
            pesos=score_data_referencia.get("pesos", {}) if score_data_referencia else {},
        )
        edifici.puntuacioBase = puntuacio
        update_fields.append("puntuacioBase")

    # --- BHS d'open data ---
    resultat_od = calcular_bhs_opendata(edifici)
    if resultat_od is not None:
        edifici.puntuacioBaseOpenData = resultat_od["score"]
        update_fields.append("puntuacioBaseOpenData")

    # --- Classificació energètica estimada ---
    resultat = calcular_classificacio_estimada(edifici)
    edifici.classificacioEstimada = resultat["classificacio"]
    edifici.classificacioFont = resultat["font"]
    update_fields.extend(["classificacioEstimada", "classificacioFont"])

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


# --- NOU: recalcular quan canvien les dades open data ---
@receiver(post_save, sender=DadesEnergetiquesOpenData)
@receiver(post_delete, sender=DadesEnergetiquesOpenData)
def signal_dades_opendata(sender, instance, **kwargs):
    _recalcular_edifici(instance.edifici)