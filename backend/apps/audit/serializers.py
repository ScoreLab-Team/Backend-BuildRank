from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True, default=None)

    class Meta:
        model = AuditLog
        fields = [
            'id',
            'user',
            'user_email',
            'method',
            'endpoint',
            'resource_type',
            'resource_id',
            'status_code',
            'ip_address',
            'user_agent',
            'duration_ms',
            'timestamp',
        ]
