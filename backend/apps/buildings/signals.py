from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import Habitatge, DadesEnergetiques
from .scoring import calcular_building_health_score

@receiver(post_save, sender=Habitatge)
@receiver(post_delete, sender=Habitatge)
@receiver(post_save, sender=DadesEnergetiques)
@receiver(post_delete, sender=DadesEnergetiques)
def actualizar_bhs_edificio(sender, instance, **kwargs):
    edificio = instance.edifici
    if not edificio:
        return

    # Loop por todos los habitatges del edificio
    scores = []
    for h in edificio.habitatges.all():
        if hasattr(h, "dadesEnergetiques"):
            score_data = calcular_building_health_score(h.dadesEnergetiques)
            scores.append(score_data["score"])
            print(f"[DEBUG] BHS calculado para {h.referenciaCadastral}: {score_data['score']}")

    if scores:
        promedio = sum(scores) / len(scores)

        # Guardar en la historia
        edificio.bhs_history.create(
            score=promedio,
            version="1.0",
            pesos={}
        )

        # Actualizar el campo actual del edificio
        edificio.puntuacioBase = promedio
        edificio.save(update_fields=["puntuacioBase"])
        print(f"[DEBUG] BHS actualizado en Edifici {edificio.idEdifici}: {edificio.puntuacioBase}")