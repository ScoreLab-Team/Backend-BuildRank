# apps/buildings/services/building_lookup.py
from apps.buildings.models import Edifici, Localitzacio


def buscar_edifici(carrer: str, numero: int | None) -> tuple[Edifici | None, str]:
    """
    Cerca l'edifici a la BD seguint dos nivells de precisió:
      1. Coincidència exacta: carrer + número.
      2. Coincidència per carrer: qualsevol edifici actiu del mateix carrer.

    Retorna (edifici, nivell_coincidencia).
    nivell_coincidencia: "exacta" | "carrer" | "cap"
    """
    print(f"Buscant edifici per carrer='{carrer}' i numero='{numero}'")
    qs_carrer = Localitzacio.objects.filter(
        carrer__iexact=carrer,
        edifici__actiu=True,
    ).select_related("edifici")

    print(f"Localitzacions trobades al carrer '{carrer}': {qs_carrer.count()}")
    if not qs_carrer.exists():
        return None, "cap"

    if numero is not None:
        loc_exacta = qs_carrer.filter(numero=numero).first()
        if loc_exacta and loc_exacta.edifici:
            return loc_exacta.edifici, "exacta"

    loc_carrer = qs_carrer.first()
    if loc_carrer and loc_carrer.edifici:
        return loc_carrer.edifici, "carrer"

    return None, "cap"