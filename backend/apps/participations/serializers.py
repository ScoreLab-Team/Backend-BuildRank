from rest_framework import serializers
from .models import Participacio


class ParticipacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participacio
        fields = "__all__"

class RankingSerializer(serializers.ModelSerializer):
    edifici = serializers.IntegerField(source="edifici.idEdifici")
    nom = serializers.CharField(source="edifici.__str__", read_only=True)

    adreca = serializers.SerializerMethodField()

    lliga = serializers.IntegerField(source="lliga.id")
    nom_lliga = serializers.CharField(source="lliga.nom", read_only=True)

    temporada = serializers.IntegerField(source="lliga.temporada.id_temporada")
    nom_temporada = serializers.CharField(source="lliga.temporada.nom", read_only=True)

    grup_comparable = serializers.IntegerField(
        source="edifici.grupComparable.idGrup",
        allow_null=True
    )

    class Meta:
        model = Participacio
        fields = [
            "edifici",
            "nom",
            "adreca",
            "puntuacio",
            "posicio",
            "grup_comparable",
            "lliga",
            "nom_lliga",
            "temporada",
            "nom_temporada",
        ]

    def get_adreca(self, obj):
        loc = obj.edifici.localitzacio
        if not loc:
            return None
        return f"{loc.carrer}, {loc.numero}"