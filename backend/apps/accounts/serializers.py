from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Profile, RoleChoices
from apps.buildings.models import Edifici, Habitatge

from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

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
            raise serializers.ValidationError(
                {"password_confirm": "Les contrasenyes no coincideixen."}
            )

        requested_role = attrs.get("role")
        if requested_role == RoleChoices.ADMIN:
            raise serializers.ValidationError(
                {"role": "No està permès registrar-se com a administrador."}
            )

        password = attrs["password"]

        if not any(char.isalpha() for char in password):
            raise serializers.ValidationError(
                {"password": "La contrasenya ha de contenir almenys una lletra."}
            )

        if not any(char.isdigit() for char in password):
            raise serializers.ValidationError(
                {"password": "La contrasenya ha de contenir almenys un número."}
            )

        temp_user = User(
            email=attrs.get("email", ""),
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
        )

        try:
            validate_password(password, user=temp_user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

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

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.role = role
        profile.save(update_fields=["role"])

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


class LocalitzacioResum(serializers.Serializer):
    carrer = serializers.CharField()
    numero = serializers.IntegerField()
    codiPostal = serializers.CharField()
    barri = serializers.CharField()
    zonaClimatica = serializers.CharField()

class EdificiResumSerializer(serializers.ModelSerializer):
    localitzacio = LocalitzacioResum(read_only=True)

    class Meta:
        model = Edifici
        fields = ("idEdifici", "tipologia", "superficieTotal", "puntuacioBase", "localitzacio")

class HabitatgeResumSerializer(serializers.ModelSerializer):
    edifici_id = serializers.CharField(source="edifici.idEdifici", read_only=True)

    class Meta:
        model = Habitatge
        fields = ("referenciaCadastral", "planta", "porta", "superficie", "edifici_id")

# ---------------------------------------------------------------------------
# Assignació
# ---------------------------------------------------------------------------

class AssignarResidentSerializer(serializers.Serializer):
    """Assigna un usuari (resident) a un habitatge."""
    user_id = serializers.IntegerField()

    def validate_user_id(self, value):
        if not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Usuari no trobat.")
        return value


class AssignarAdminSerializer(serializers.Serializer):
    """Assigna un administrador de finca a un edifici."""
    user_id = serializers.IntegerField(allow_null=True)

    def validate_user_id(self, value):
        if value is not None and not User.objects.filter(pk=value).exists():
            raise serializers.ValidationError("Usuari no trobat.")
        return value

class AccountUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name")

    def update(self, instance, validated_data):
        instance.first_name = validated_data.get("first_name", instance.first_name)
        instance.last_name = validated_data.get("last_name", instance.last_name)
        instance.save(update_fields=["first_name", "last_name"])
        return instance