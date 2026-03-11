# apps/buildings/serializers.py
from rest_framework import serializers
from .models import Edifici, Habitatge, DadesEnergetiques, Localitzacio

class LocalitzacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Localitzacio
        fields = "__all__"

class DadesEnergetiquesSerializer(serializers.ModelSerializer):
    class Meta:
        model = DadesEnergetiques
        fields = "__all__"

class HabitatgeSerializer(serializers.ModelSerializer):
    dades_energetiques = DadesEnergetiquesSerializer(read_only=True)

    class Meta:
        model = Habitatge
        fields = "__all__"

class EdificiSerializer(serializers.ModelSerializer):
    habitatges = HabitatgeSerializer(many=True, read_only=True)
    localitzacio = LocalitzacioSerializer(read_only=True)

    class Meta:
        model = Edifici
        fields = "__all__"