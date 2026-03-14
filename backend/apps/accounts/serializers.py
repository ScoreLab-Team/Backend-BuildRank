from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import Profile, RoleChoices, Edifici, Localitzacio, Habitatge

from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

from datetime import date
import re

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

        requested_role = attrs.get("role")
        if requested_role == RoleChoices.ADMIN:
            raise serializers.ValidationError({"role": "No està permès registrar-se com a administrador."})

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


# ---------------------------------------------------------------------------
# Edifici / Habitatge
# ---------------------------------------------------------------------------

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


class EdificiSerializer(serializers.ModelSerializer):
    class Meta:
        model = Edifici
        fields = '__all__'

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


class LocalitzacioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Localitzacio
        fields = '__all__'

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


class HabitatgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Habitatge
        fields = '__all__'

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