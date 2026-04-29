from rest_framework import serializers
from .models import Participacio


class ParticipacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participacio
        fields = "__all__"