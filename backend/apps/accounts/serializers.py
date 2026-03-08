from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Profile, RoleChoices

from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=RoleChoices.choices, required=False)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "password", "password_confirm", "role")

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Ja existeix un usuari amb aquest email.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Les contrasenyes no coincideixen."})

        password = attrs["password"]

        if not any(char.isalpha() for char in password):
            raise serializers.ValidationError({"password": "La contrasenya ha de contenir almenys una lletra."})

        if not any(char.isdigit() for char in password):
            raise serializers.ValidationError({"password": "La contrasenya ha de contenir almenys un número."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        role = validated_data.pop("role", RoleChoices.OWNER)
        validated_data.pop("password_confirm")

        password = validated_data.pop("password")

        user = User.objects.create_user(
            password=password,
            **validated_data,
        )

        Profile.objects.create(user=user, role=role)

        return user
    
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError("Credencials invàlides.")

        if not user.is_active:
            raise serializers.ValidationError("Aquest usuari està inactiu.")

        refresh = RefreshToken.for_user(user)

        return {
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()

    def validate_refresh(self, value):
        if not value:
            raise serializers.ValidationError("El refresh token és obligatori.")
        return value

    def save(self, **kwargs):
        try:
            refresh_token = self.validated_data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception:
            raise serializers.ValidationError({"refresh": "Token invàlid o ja invalidat."})

class MeSerializer(serializers.ModelSerializer):
    role = serializers.CharField(source="profile.role")

    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "role")