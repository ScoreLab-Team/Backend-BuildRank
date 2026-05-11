from rest_framework import serializers
from .models import Lliga


class LligaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lliga
        fields = "__all__"