# apps/buildings/serializers.py
from django.db.models import Q
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
    EstatValidacio,
    TipusEdifici,
    TipusOrientacio,
    VotacioSimulacioMillora,
    VotSimulacioMillora,
    SentitVotSimulacio,
    RolVinculacioHabitatge,
)
import re
from datetime import date

from apps.accounts.models import RoleChoices
from .scoring import calcular_classificacio_estimada, calcular_heat_risk_index
from apps.buildings.services.badges import get_badges_resum_edifici
from django.db import transaction
from django.contrib.auth import get_user_model

User = get_user_model()

class UsuariBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'email']

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
    solicitant = UsuariBasicSerializer(read_only=True)

    propietari = UsuariBasicSerializer(read_only=True)
    llogater = UsuariBasicSerializer(read_only=True)
    rolSolicitat = serializers.ChoiceField(
        choices=RolVinculacioHabitatge.choices,
        required=False,
        allow_null=True
    )

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
        # bloquegem aquests camps perquè l'usuari no els pugui manipular durant el POST
        read_only_fields = ['estatValidacio', 'solicitant', 'usuari', 'propietari', 'llogater', 'rolSolicitat']

class DadesEnergetiquesUpdateSerializer(serializers.ModelSerializer):
    """Per crear o actualitzar DadesEnergetiques des de l'endpoint de l'habitatge."""
    class Meta:
        model = DadesEnergetiques
        fields = "__all__"
        # id és read_only per evitar que el frontend intenti forçar un id
        read_only_fields = ['id']


class HabitatgeMeUpdateSerializer(serializers.ModelSerializer):
    """PATCH /edificis/<id>/me/habitatge/ — camps editables per l'owner/tenant."""
    dadesEnergetiques = DadesEnergetiquesUpdateSerializer(required=False)

    class Meta:
        model = Habitatge
        fields = ['planta', 'porta', 'superficie', 'anyReforma', 'dadesEnergetiques']

    def validate_superficie(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La superfície de l'habitatge ha de ser més gran que 0."
            )
        return value

    def validate_anyReforma(self, value):
        if value is not None:
            any_actual = date.today().year
            if value > any_actual:
                raise serializers.ValidationError(
                    f"L'any de reforma no pot ser del futur (màxim {any_actual})."
                )
        return value

    def validate(self, data):
        any_reforma = data.get('anyReforma')
        # self.instance és l'habitatge existent (estem sempre en update)
        if any_reforma is not None and self.instance:
            any_construccio = self.instance.edifici.anyConstruccio
            if any_reforma < any_construccio:
                raise serializers.ValidationError({
                    "anyReforma": (
                        f"L'any de reforma ({any_reforma}) no pot ser anterior "
                        f"a l'any de construcció de l'edifici ({any_construccio})."
                    )
                })
        return data

    def update(self, instance, validated_data):
        dades_data = validated_data.pop('dadesEnergetiques', None)

        # Actualitzar camps bàsics de l'habitatge
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Gestionar dadesEnergetiques només si venen al payload
        if dades_data is not None:
            with transaction.atomic():
                if instance.dadesEnergetiques:
                    # Actualitzar les existents
                    de = instance.dadesEnergetiques
                    for attr, value in dades_data.items():
                        setattr(de, attr, value)
                    de.save()
                else:
                    # Crear i vincular
                    de = DadesEnergetiques.objects.create(**dades_data)
                    instance.dadesEnergetiques = de
                    instance.save(update_fields=["dadesEnergetiques"])

        return instance
    
class EdificiCercaSerializer(serializers.ModelSerializer):
    # Això és el que fa que el JSON inclogui l'objecte localització sencer
    localitzacio = LocalitzacioSerializer(read_only=True)

    class Meta:
        model = Edifici
        fields = ['idEdifici', 'localitzacio', 'anyConstruccio']

# Edifici 1. Llistat lleuger
class EdificiListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edifici
        fields = ['idEdifici', 'localitzacio', 'tipologia', 'anyConstruccio', 'superficieTotal', 'puntuacioBase']

class EdificiMapSerializer(serializers.ModelSerializer):
    """
    Serializer lleuger per representar edificis al mapa en format GeoJSON.

    No exposa dades personals, habitatges ni informació sensible.
    Només retorna dades agregades i visuals de l'edifici.
    """
    type = serializers.SerializerMethodField()
    id = serializers.IntegerField(source="idEdifici", read_only=True)
    geometry = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()

    class Meta:
        model = Edifici
        fields = ["type", "id", "geometry", "properties"]

    def get_type(self, obj):
        return "Feature"

    def get_geometry(self, obj):
        loc = obj.localitzacio

        return {
            "type": "Point",
            "coordinates": [
                loc.longitud,
                loc.latitud,
            ],
        }

    def get_properties(self, obj):
        loc = obj.localitzacio

        score = obj.puntuacioBase
        if score is None:
            score = obj.puntuacioBaseOpenData

        score_label = self._score_label(score)

        carrer = (loc.carrer or "").strip()
        numero = loc.numero
        barri = (loc.barri or "").strip()
        codi_postal = (loc.codiPostal or "").strip()

        titol = f"{carrer}, {numero}" if carrer else f"Edifici {obj.idEdifici}"

        adreca_parts = [
            titol,
            barri,
            codi_postal,
        ]

        return {
            "idEdifici": obj.idEdifici,
            "titol": titol,
            "adreca": " · ".join([part for part in adreca_parts if part]),
            "barri": barri,
            "codiPostal": codi_postal,
            "tipologia": obj.tipologia,
            "anyConstruccio": obj.anyConstruccio,
            "superficieTotal": obj.superficieTotal,
            "puntuacioBase": round(score, 2) if score is not None else None,
            "puntuacioLabel": score_label,
            "classificacioEstimada": obj.classificacioEstimada,
            "classificacioFont": obj.classificacioFont,
            "fontOpenData": obj.font_open_data,
            "procedenciaDades": self.get_procedencia_dades(obj),
            "bhs": self.get_bhs_summary(obj, score),
            "heatRisk": self.get_heat_risk_summary(obj),
            "badgesSummary": self.get_badges_summary(obj),
            "detailEndpoint": f"/api/buildings/edificis/{obj.idEdifici}/",
        }

    def _score_label(self, score):
        if score is None:
            return "SENSE_DADES"
        if score >= 80:
            return "EXCEL·LENT"
        if score >= 65:
            return "BO"
        if score >= 50:
            return "MILLORABLE"
        return "PRIORITARI"

    def _round_nullable(self, value):
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _score_font(self, obj):
        if getattr(obj, "puntuacioBase", None) is not None:
            return "usuaris"
        if getattr(obj, "puntuacioBaseOpenData", None) is not None:
            return "open_data"
        return "sense_dades"

    def get_procedencia_dades(self, obj):
        score_font = self._score_font(obj)

        if getattr(obj, "font_open_data", False) or score_font == "open_data":
            return {
                "tipus": "open_data",
                "label": "Open Data / registre oficial",
                "descripcio": "Dades procedents de fonts obertes o registres oficials integrats al sistema.",
                "esOficial": True,
                "esEstimada": False,
            }

        if score_font == "usuaris":
            return {
                "tipus": "usuaris",
                "label": "Dades aportades o validades per la comunitat",
                "descripcio": "Informació calculada a partir de dades introduïdes o revisades dins de BuildRank.",
                "esOficial": False,
                "esEstimada": True,
            }

        return {
            "tipus": "insuficient",
            "label": "Dades insuficients",
            "descripcio": "Encara no hi ha prou informació pública per calcular indicadors fiables.",
            "esOficial": False,
            "esEstimada": True,
        }

    def get_bhs_summary(self, obj, score=None):
        font = self._score_font(obj)

        if score is None:
            score = (
                getattr(obj, "puntuacioBase", None)
                if getattr(obj, "puntuacioBase", None) is not None
                else getattr(obj, "puntuacioBaseOpenData", None)
            )

        rounded_score = self._round_nullable(score)

        if rounded_score is None:
            label = "Sense puntuació"
        elif rounded_score >= 85:
            label = "Excel·lent"
        elif rounded_score >= 70:
            label = "Notable"
        elif rounded_score >= 50:
            label = "Correcte"
        else:
            label = "Millorable"

        return {
            "score": rounded_score,
            "font": font,
            "label": label,
            "rankejable": rounded_score is not None,
        }

    def get_heat_risk_summary(self, obj):
        index = self._round_nullable(getattr(obj, "heatRiskIndex", None))
        font = getattr(obj, "heatRiskFont", None)

        if index is None:
            etiqueta = "Sense dades"
        elif index >= 75:
            etiqueta = "Risc alt"
        elif index >= 50:
            etiqueta = "Risc mitjà"
        elif index >= 25:
            etiqueta = "Risc moderat"
        else:
            etiqueta = "Risc baix"

        return {
            "index": index,
            "font": font,
            "etiqueta": etiqueta,
        }

    def get_badges_summary(self, obj):
        try:
            return get_badges_resum_edifici(obj, limit=3)
        except Exception:
            return []


def _etiqueta_font(font: str | None) -> str:
    """Retorna una etiqueta llegible per a la UI segons l'origen de la classificació."""
    etiquetes = {
        'oficial':     'Classificació oficial CEE',
        'estimada':    'Classificació estimada',
        'insuficient': 'Dades insuficients',
    }
    return etiquetes.get(font, '— Sense classificació')

# Edifici 2. Detall públic (localitzacio anidada + camps extra)

class EdificiDetailSerializer(serializers.ModelSerializer):
    localitzacio = LocalitzacioSerializer(read_only=True)

    # Camp d'escriptura per crear/actualitzar la relació amb una localització existent.
    # El frontend envia localitzacioId, i el backend retorna localitzacio anidada.
    localitzacioId = serializers.PrimaryKeyRelatedField(
        source="localitzacio",
        queryset=Localitzacio.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    # US15: Classificació energètica estimada/oficial/insuficient.
    classificacio_energetica = serializers.SerializerMethodField(
        help_text="Classificació energètica de l'edifici. Pot ser oficial, estimada o insuficient."
    )

    heat_risk = serializers.SerializerMethodField(
        help_text="Heat Risk Index de l'edifici (0–100). Null si manquen dades."
    )

    # Habitatges visibles segons el rol de l'usuari autenticat.
    habitatges = serializers.SerializerMethodField()

    class Meta:
        model = Edifici
        fields = [
            "idEdifici",
            "anyConstruccio",
            "tipologia",
            "superficieTotal",
            "nombrePlantes",
            "reglament",
            "orientacioPrincipal",
            "puntuacioBase",
            "puntuacioBaseOpenData",
            "classificacioEstimada",
            "classificacioFont",
            "font_open_data",
            "num_cas_origen",
            "tipologia_open_data",
            "classificacio_energetica",
            "heat_risk",
            "actiu",
            "dataDesactivacio",
            "motivDesactivacio",
            "localitzacio",
            "localitzacioId",
            "administradorFinca",
            "grupComparable",
            "habitatges",
        ]
        read_only_fields = [
            "idEdifici",
            "puntuacioBase",
            "puntuacioBaseOpenData",
            "classificacioEstimada",
            "classificacioFont",
            "font_open_data",
            "num_cas_origen",
            "tipologia_open_data",
            "classificacio_energetica",
            "heat_risk",
            "actiu",
            "dataDesactivacio",
            "motivDesactivacio",
            "localitzacio",
            "administradorFinca",
            "grupComparable",
            "habitatges",
        ]

    def get_classificacio_energetica(self, obj):
        """
        Retorna la classificació energètica amb tota la informació necessària
        perquè la UI pugui diferenciar si és oficial, estimada o insuficient.
        """
        resultat = calcular_classificacio_estimada(obj)

        return {
            "lletra": resultat["classificacio"],
            "font": resultat["font"],
            "etiqueta": _etiqueta_font(resultat["font"]),
            "detall": resultat["detall"],
            "dades_insuficients": resultat.get("dades_insuficients"),
        }

    def get_heat_risk(self, obj):
        resultat = calcular_heat_risk_index(obj)
        index = resultat["index"]

        if index is None:
            etiqueta = "Sense dades"
        elif index >= 75:
            etiqueta = "Risc alt"
        elif index >= 50:
            etiqueta = "Risc moderat"
        elif index >= 25:
            etiqueta = "Risc baix"
        else:
            etiqueta = "Risc molt baix"

        return {
            "index": index,
            "font": resultat["font"],
            "etiqueta": etiqueta,
            "dades_insuficients": resultat["dades_insuficients"] or None,
        }

    def get_habitatges(self, obj):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            return []

        user = request.user
        role = getattr(getattr(user, "profile", None), "role", None)

        if user.is_superuser:
            qs = obj.habitatges.all()
        elif role == RoleChoices.ADMIN:
            from apps.verification.access import admin_assignment_is_effective

            if admin_assignment_is_effective(user, obj):
                # Administrador de finca efectiu: veu tots els habitatges de l'edifici que administra.
                qs = obj.habitatges.all()
            else:
                qs = obj.habitatges.none()
        else:
            # Owner/Tenant: només veu els habitatges vinculats al seu usuari.
            qs = obj.habitatges.filter(Q(usuari=user) | Q(propietari=user) | Q(llogater=user))

        return HabitatgeResumSerializer(qs, many=True).data

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
    costOrientatiuUnitari = serializers.FloatField(
        source="cost_orientatiu_unitari",
        read_only=True,
    )

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
            'costOrientatiuUnitari',
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
            raise serializers.ValidationError("Cal seleccionar com a m?nim una millora.")

        ids = [item["milloraId"] for item in value]

        if len(ids) != len(set(ids)):
            raise serializers.ValidationError(
                "No es pot seleccionar la mateixa millora m?s d'una vegada en una simulaci?."
            )

        existing_ids = set(
            CatalegMillora.objects
            .filter(idMillora__in=ids, activa=True)
            .values_list("idMillora", flat=True)
        )

        missing = sorted(set(ids) - existing_ids)
        if missing:
            raise serializers.ValidationError(
                f"Les millores seg?ents no existeixen o no estan actives: {missing}"
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
            'estatAplicacio',
            'votacioAprovadaAt',
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


class ValidacioMilloraSerializer(serializers.Serializer):
    ESTATS_PERMESOS = [EstatValidacio.VALIDADA, EstatValidacio.REBUTJADA]

    estatValidacio = serializers.ChoiceField(choices=ESTATS_PERMESOS)
    observacionsAdmin = serializers.CharField(required=False, allow_blank=True, default="")

class VotSimulacioMilloraSerializer(serializers.ModelSerializer):
    usuariEmail = serializers.EmailField(source='usuari.email', read_only=True)

    class Meta:
        model = VotSimulacioMillora
        fields = [
            'id',
            'usuari',
            'usuariEmail',
            'sentit',
            'data',
        ]
        read_only_fields = fields


class VotacioSimulacioMilloraSerializer(serializers.ModelSerializer):
    simulacio = SimulacioMilloraSerializer(read_only=True)
    totalVots = serializers.SerializerMethodField()
    votsFavor = serializers.SerializerMethodField()
    votsContra = serializers.SerializerMethodField()
    participacioPercent = serializers.SerializerMethodField()
    favorPercent = serializers.SerializerMethodField()
    potVotar = serializers.SerializerMethodField()
    elMeuVot = serializers.SerializerMethodField()

    class Meta:
        model = VotacioSimulacioMillora
        fields = [
            'id',
            'titol',
            'descripcio',
            'edifici',
            'simulacio',
            'dataInici',
            'dataFi',
            'quorumPercent',
            'majoriaPercent',
            'estat',
            'totalVots',
            'votsFavor',
            'votsContra',
            'participacioPercent',
            'favorPercent',
            'potVotar',
            'elMeuVot',
        ]
        read_only_fields = fields

    def _electors_count(self, obj):
        admin_count = 1 if obj.edifici.administradorFinca_id else 0
        owners_count = obj.edifici.habitatges.filter(
            usuari__isnull=False,
            usuari__profile__role='owner',
        ).values('usuari').distinct().count()
        return max(admin_count + owners_count, 1)

    def get_totalVots(self, obj):
        return obj.total_vots

    def get_votsFavor(self, obj):
        return obj.vots_favor

    def get_votsContra(self, obj):
        return obj.vots_contra

    def get_participacioPercent(self, obj):
        total = self._electors_count(obj)
        return round((obj.total_vots / total) * 100, 2)

    def get_favorPercent(self, obj):
        total_vots = obj.total_vots
        if total_vots == 0:
            return 0
        return round((obj.vots_favor / total_vots) * 100, 2)

    def get_potVotar(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        user = request.user

        if obj.edifici.administradorFinca_id == user.id:
            return True

        return obj.edifici.habitatges.filter(
            usuari=user,
            usuari__profile__role='owner',
        ).exists()

    def get_elMeuVot(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None

        vot = obj.vots.filter(usuari=request.user).first()
        return vot.sentit if vot else None


class CrearVotacioSimulacioSerializer(serializers.Serializer):
    titol = serializers.CharField(max_length=255, required=False, allow_blank=True)
    descripcio = serializers.CharField(required=False, allow_blank=True, default='')
    dataFi = serializers.DateTimeField(required=False)
    diesDurada = serializers.IntegerField(required=False, min_value=1, max_value=90, default=14)
    quorumPercent = serializers.FloatField(required=False, min_value=1, max_value=100, default=75)
    majoriaPercent = serializers.FloatField(required=False, min_value=1, max_value=100, default=50)


class VotarSimulacioSerializer(serializers.Serializer):
    sentit = serializers.ChoiceField(choices=SentitVotSimulacio.choices)


class AcreditarSimulacioImplementadaSerializer(serializers.Serializer):
    dataExecucio = serializers.DateField()
    costReal = serializers.FloatField(min_value=0)
    documentacioAdjunta = serializers.FileField()

    def validate_documentacioAdjunta(self, value):
        allowed = {
            'application/pdf',
            'image/jpeg',
            'image/png',
            'image/webp',
        }

        if value.content_type not in allowed:
            raise serializers.ValidationError(
                "Només es permet documentació PDF, JPG, PNG o WEBP."
            )

        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(
                "El fitxer no pot superar els 10 MB."
            )

        return value

class ReclamarEdificiAdminSerializer(serializers.Serializer):
    carrer = serializers.CharField(max_length=255)
    numero = serializers.IntegerField()
    codiPostal = serializers.CharField(max_length=10)
    anyConstruccio = serializers.IntegerField(required=False, default=1980)
    tipologia = serializers.ChoiceField(
        choices=TipusEdifici.choices,
        required=False,
        default=TipusEdifici.RESIDENCIAL,
    )
    superficieTotal = serializers.FloatField(required=False, default=1000.0)

    # Camps obligatoris al model Edifici. Els donem permesos/default
    # per no trencar l'alta d'edifici quan el frontend encara no els envia.
    reglament = serializers.CharField(
        max_length=100,
        required=False,
        default="Desconegut",
    )
    orientacioPrincipal = serializers.ChoiceField(
        choices=TipusOrientacio.choices,
        required=False,
        default=TipusOrientacio.SUD,
    )

    def validate_codiPostal(self, value):
        if not re.match(r'^\d{5}$', value):
            raise serializers.ValidationError(
                "El format del codi postal és incorrecte. Han de ser 5 dígits."
            )
        return value