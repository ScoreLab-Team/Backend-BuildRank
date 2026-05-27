from rest_framework import serializers
from .models import Notificacio


class NotificacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacio
        fields = ['id', 'tipus', 'titol', 'cos', 'llegida', 'dataCreacio', 'objecte_id']
        read_only_fields = fields
