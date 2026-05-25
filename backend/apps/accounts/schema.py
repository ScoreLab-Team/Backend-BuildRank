from drf_spectacular.extensions import OpenApiAuthenticationExtension
from rest_framework import serializers


class AccountStatusJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.accounts.authentication.AccountStatusJWTAuthentication"
    name = "BearerAuth"
    match_subclasses = True

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "JWT Bearer token. Use the Authorization header with value: Bearer <access_token>.",
        }


class AuthUserResponseSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    first_name = serializers.CharField(allow_blank=True)
    last_name = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_null=True)


class AuthTokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = AuthUserResponseSerializer()


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class AdminDashboardSummarySerializer(serializers.Serializer):
    users_total = serializers.IntegerField()
    buildings_total = serializers.IntegerField()
    buildings_managed = serializers.IntegerField()
    pending_improvements = serializers.IntegerField()
    pending_admin_verifications = serializers.IntegerField()
    pending_housing_requests = serializers.IntegerField()
    active_season = serializers.JSONField(allow_null=True)
