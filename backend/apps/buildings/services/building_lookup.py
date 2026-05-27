# apps/buildings/services/building_lookup.py
from apps.buildings.models import Edifici, Localitzacio
from apps.buildings.services.normalitzacio import normalitzar_carrer


def buscar_edifici(carrer: str, numero: int | None) -> tuple[Edifici | None, str]:
    carrer_norm = normalitzar_carrer(carrer)
    print(f"Buscant edifici per carrer='{carrer}' (norm='{carrer_norm}') i numero='{numero}'")

    totes = Localitzacio.objects.filter(
        edifici__actiu=True
    ).select_related("edifici")

    qs_carrer = [loc for loc in totes if normalitzar_carrer(loc.carrer) == carrer_norm]

    print(f"Localitzacions trobades al carrer '{carrer_norm}': {len(qs_carrer)}")
    if not qs_carrer:
        return None, "cap"

    if numero is not None:
        loc_exacta = next((loc for loc in qs_carrer if loc.numero == numero), None)
        if loc_exacta and loc_exacta.edifici:
            return loc_exacta.edifici, "exacta"

    loc_carrer = qs_carrer[0]
    if loc_carrer and loc_carrer.edifici:
        return loc_carrer.edifici, "carrer"

    return None, "cap"