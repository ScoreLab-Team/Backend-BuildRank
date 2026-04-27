# apps/buildings/serializers.py
from rest_framework import serializers
from apps.buildings.models import (
    Edifici,
    Habitatge,
    DadesEnergetiques,
    Localitzacio,
    carrersBarcelona,
    CatalegMillora,
    SimulacioMillora,
    SimulacioMilloraItem,
    MilloraImplementada,
)
import re
from datetime import date


class LocalitzacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Localitzacio
        fields = "__all__"
    
    # validacio codi postal (5 digits numerics)
    def validate_codiPostal(self, value):
        if not re.match(r'^\d{5}$', value):
            raise serializers.ValidationError(
                "El format del codi postal és incorrecte. Han de ser 5 dígits."
            )
        return value

    # validacio rang latitud (entre -90 i 90)
    def validate_latitud(self, value):
        if value < -90 or value > 90:
            raise serializers.ValidationError(
                "La latitud ha de ser un valor entre -90 i 90."
            )
        return value
    
    # validacio rang longitud (entre -180 i 180)
    def validate_longitud(self, value):
        if value < -180 or value > 180:
            raise serializers.ValidationError(
                "La longitud ha de ser un valor entre -180 i 180."
            )
        return value
    
    # validacio localitzacio (comprovar que la direccio existeix a OSM)
    def validate(self, data):
        carrer = data.get("carrer")
        numero = data.get("numero")

        if not carrer or numero is None:
            raise serializers.ValidationError("La direcció és incompleta.")

        carrers = carrersBarcelona.objects.filter(nom_oficial__iexact=carrer)

        if not carrers.exists():
            raise serializers.ValidationError(
                f"El carrer '{carrer}' no existeix a la base de dades de carrers."
            )

        numero_valid = False
        rangs_disponibles = []

        for carrer_obj in carrers:
            nre_min = carrer_obj.nre_min
            nre_max = carrer_obj.nre_max

            if nre_min is not None and nre_max is not None:
                rangs_disponibles.append(f"{nre_min}-{nre_max}")

            min_ok = nre_min is None or numero >= nre_min
            max_ok = nre_max is None or numero <= nre_max

            if min_ok and max_ok:
                numero_valid = True
                break

        if not numero_valid:
            rangs_text = ", ".join(rangs_disponibles) if rangs_disponibles else "rang no informat"
            raise serializers.ValidationError(
                f"El número {numero} no està dins del rang permès per {carrer}. "
                f"Rangs disponibles: {rangs_text}."
            )

        return data

class DadesEnergetiquesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DadesEnergetiques
        fields = "__all__"
    

# Resum habitatge (sense dades energètiques)
class HabitatgeResumSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habitatge
        fields = ['referenciaCadastral', 'planta', 'porta', 'superficie', 'anyReforma']

# Detall habitatge complet (protegit)
class HabitatgeDetailSerializer(serializers.ModelSerializer):
    dadesEnergetiques = DadesEnergetiquesSerializer(read_only=True)

    # validacio superficie
    def validate_superficie(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La superfície de l'habitatge ha de ser més gran que 0."
            )
        return value
    
    # validacio any reforma
    def validate(self, data):
        any_reforma = data.get('anyReforma')
        edifici = data.get('edifici')

        if any_reforma is not None:
            # comprovem que no sigui del futur
            any_actual = date.today().year
            if any_reforma > any_actual:
                raise serializers.ValidationError({
                    "anyReforma": f"L'any de reforma no pot ser del futur (màxim {any_actual})."
                })
            
            # comprovem que no sigui anterior a la construccio de l'edifici
            if edifici and any_reforma < edifici.anyConstruccio:
                raise serializers.ValidationError({
                    "anyReforma": f"L'any de reforma ({any_reforma}) no pot ser anterior a l'any de construcció de l'edifici ({edifici.anyConstruccio})."
                })

        return data

    class Meta:
        model = Habitatge
        unique_together = ('edifici', 'planta', 'porta')
        fields = '__all__'


# Edifici 1. Llistat lleuger
class EdificiListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edifici
        fields = ['idEdifici', 'tipologia', 'anyConstruccio', 'superficieTotal', 'puntuacioBase']

# Edifici 2. Detall públic (localitzacio anidada + camps extra)
class EdificiDetailSerializer(serializers.ModelSerializer):
    localitzacio = LocalitzacioSerializer(read_only=True)

    # Camp d'escriptura per crear/actualitzar la relació amb una localització existent.
    # El frontend envia localitzacioId, i el backend retorna localitzacio anidada.
    localitzacioId = serializers.PrimaryKeyRelatedField(
        source='localitzacio',
        queryset=Localitzacio.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Edifici
        fields = [
            'idEdifici',
            'anyConstruccio',
            'tipologia',
            'superficieTotal',
            'nombrePlantes',
            'reglament',
            'orientacioPrincipal',
            'puntuacioBase',
            'actiu',
            'dataDesactivacio',
            'motivDesactivacio',
            'localitzacio',
            'localitzacioId',
            'administradorFinca',
            'grupComparable',
        ]
        read_only_fields = [
            'idEdifici',
            'puntuacioBase',
            'actiu',
            'dataDesactivacio',
            'motivDesactivacio',
            'localitzacio',
            'administradorFinca',
            'grupComparable',
        ]

    def get_bhs(self, obj):
        last_bhs = obj.bhs_history.first()
        if last_bhs:
            return {
                "score": last_bhs.score,
                "version": last_bhs.version,
                "pesos": last_bhs.pesos,
            }
        return None

    def validate_anyConstruccio(self, value):
        any_actual = date.today().year
        if value < 1800 or value > any_actual:
            raise serializers.ValidationError(
                f"L'any de construcció ha de ser entre 1800 i {any_actual}"
            )
        return value

    def validate_superficieTotal(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La superfície total ha de ser més gran que 0."
            )
        return value

class RankingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edifici
        fields = ['idEdifici','puntuacioBase'] #Afegir posició

class CatalegMilloraSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalegMillora
        fields = [
            'idMillora',
            'slug',
            'nom',
            'descripcio',
            'categoria',
            'activa',
            'unitatBase',
            'costEstimatBase',
            'mantenimentAnual',
            'vidaUtil',
            'estalviEnergeticEstimat',
            'impactePunts',
            'nivellConfianca',
            'ambit',
            'requereixAcordComunitat',
            'tipusAcordEstimat',
            'requereixLlicenciaMunicipal',
            'requereixTecnicCompetent',
            'requereixCeePrePost',
            'bloquejadorsFrequents',
            'parametresBase',
        ]


class SimulacioMilloraItemInputSerializer(serializers.Serializer):
    milloraId = serializers.IntegerField()
    quantitat = serializers.FloatField(required=False, allow_null=True, min_value=0)
    coberturaPercent = serializers.FloatField(required=False, default=100, min_value=0, max_value=100)


class SimulacioMilloraPreviewSerializer(serializers.Serializer):
    descripcio = serializers.CharField(required=False, allow_blank=True, default="")
    millores = SimulacioMilloraItemInputSerializer(many=True)

    def validate_millores(self, value):
        if not value:
            raise serializers.ValidationError("Cal seleccionar com a mínim una millora.")

        ids = [item["milloraId"] for item in value]
        existing_ids = set(
            CatalegMillora.objects
            .filter(idMillora__in=ids, activa=True)
            .values_list("idMillora", flat=True)
        )

        missing = sorted(set(ids) - existing_ids)
        if missing:
            raise serializers.ValidationError(
                f"Les millores següents no existeixen o no estan actives: {missing}"
            )

        return value


class SimulacioMilloraItemSerializer(serializers.ModelSerializer):
    millora = CatalegMilloraSerializer(read_only=True)

    class Meta:
        model = SimulacioMilloraItem
        fields = [
            'id',
            'millora',
            'quantitat',
            'coberturaPercent',
            'costEstimatParcial',
            'reduccioConsumParcial',
            'reduccioEmissionsParcial',
            'impactePuntsParcial',
            'resultatParcial',
        ]


class SimulacioMilloraSerializer(serializers.ModelSerializer):
    items = SimulacioMilloraItemSerializer(many=True, read_only=True)

    class Meta:
        model = SimulacioMillora
        fields = [
            'id',
            'descripcio',
            'edifici',
            'reduccioConsumPrevista',
            'reduccioEmissionsPrevista',
            'costEstimat',
            'estalviAnual',
            'dataSimulacio',
            'versioMotor',
            'hipotesiBase',
            'resultat',
            'items',
        ]
        read_only_fields = fields

class MilloraImplementadaSerializer(serializers.ModelSerializer):
    millora = CatalegMilloraSerializer(read_only=True)

    class Meta:
        model = MilloraImplementada
        fields = [
            "id",
            "millora",
            "dataExecucio",
            "costReal",
            "estatValidacio",
            "observacionsAdmin",
            "documentacioAdjunta",
        ]