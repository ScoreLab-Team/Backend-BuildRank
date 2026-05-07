from apps.buildings.models import GrupComparable


class BuildingSegmentator:

    @staticmethod
    def get_surface_range(surface):
        if surface < 50:
            return "0-50"
        elif surface < 100:
            return "50-100"
        elif surface < 200:
            return "100-200"
        return "200+"

    @staticmethod
    def assign_group(building):
        group, created = GrupComparable.objects.get_or_create(
            zonaClimatica=building.localitzacio.zonaClimatica,
            tipologia=building.tipologia,
            rangSuperficie=BuildingSegmentator.get_surface_range(
                building.superficieTotal
            ),
            defaults={
                "idGrup": GrupComparable.objects.count() + 1
            }
        )

        return group