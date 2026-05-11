from rest_framework import serializers
from .models import Temporada


class TemporadaSerializer(serializers.ModelSerializer):
    activa = serializers.BooleanField(read_only=True)

    class Meta:
        model = Temporada
        fields = ['id_temporada', 'nom', 'dataInici', 'dataFi', 'estat', 'activa']
        read_only_fields = ['estat', 'activa']
