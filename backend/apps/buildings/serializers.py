# apps/buildings/serializers.py
from rest_framework import serializers
from apps.buildings.models import Edifici, Habitatge, DadesEnergetiques, Localitzacio, carrersBarcelona
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

        if not carrer or not numero:
            raise serializers.ValidationError("Dirección incompleta")

        try:
            carrer_obj = carrersBarcelona.objects.get(nom_oficial__iexact=carrer)
        except carrersBarcelona.DoesNotExist:
            raise serializers.ValidationError(
                f"La calle '{carrer}' no existe en nuestra base de datos."
            )

        if numero < carrer_obj.nre_min or numero > carrer_obj.nre_max:
            raise serializers.ValidationError(
                f"El número {numero} no está en el rango permitido para {carrer} ({carrer_obj.nre_min}-{carrer_obj.nre_max})"
            )

        return data

class DadesEnergetiquesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DadesEnergetiques
        fields = "__all__"


class HabitatgeSerializer(serializers.ModelSerializer):
    dades_energetiques = DadesEnergetiquesSerializer(read_only=True)

    class Meta:
        model = Habitatge
        unique_together = ('edifici', 'planta', 'porta')
        fields = "__all__"

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


class EdificiSerializer(serializers.ModelSerializer):
    habitatges = HabitatgeSerializer(many=True, read_only=True)
    localitzacio = LocalitzacioSerializer(read_only=True)

    class Meta:
        model = Edifici
        fields = "__all__"

    def get_bhs(self, obj):
        last_bhs = obj.bhs_history.first()  # devuelve el último registrado
        if last_bhs:
            return {
                "score": last_bhs.score,
                "version": last_bhs.version,
                "pesos": last_bhs.pesos
            }
    # validacio any de construcció
    def validate_anyConstruccio(self, value):
        any_actual = date.today().year
        if value < 1800 or value > any_actual:
            raise serializers.ValidationError(
                f"L'any de construcció ha de ser entre 1800 i {any_actual}"
            )
        return value

    # validacio superficie
    def validate_superficieTotal(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "La superfície total ha de ser més gran que 0."
            )
        return value