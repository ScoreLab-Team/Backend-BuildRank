from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from rest_framework import serializers

from apps.accounts.models import Profile, RoleChoices, TokenLoginLog
from apps.buildings.models import Edifici, Habitatge

from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework_simplejwt.settings import api_settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes

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

        try:
            user = User.objects.create_user(
                password=password,
                **validated_data,
            )
        except IntegrityError:
            raise serializers.ValidationError(
                {"email": "Ja existeix un usuari amb aquest email."}
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
        jti = str(refresh.get('jti'))

        # Atomic: check limit, maybe revoke oldest, and log the new session in
        # one serializable block so concurrent logins can't all slip past the
        # count check before any of them inserts their log row.
        self._enforce_session_limit(user, jti)

        return {
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    @transaction.atomic
    def _enforce_session_limit(self, user, new_jti, max_sessions=5):
        """
        Within a single atomic transaction:
          1. Lock the user row (SELECT FOR UPDATE) to serialize concurrent logins.
          2. Revoke the oldest session if the limit is already reached.
          3. Insert the new session log row.
        """
        # Lock the user's own row for the duration of this transaction.
        #
        # Why not SELECT FOR UPDATE on TokenLoginLog rows directly?
        # Phantom-read problem at READ COMMITTED: all N concurrent threads start
        # scanning the same existing rows simultaneously, each sees count < limit,
        # and all insert without revoking — even with FOR UPDATE.
        #
        # Locking the User row (which always exists) serializes threads properly:
        # thread 2 blocks on the User row lock while thread 1 holds it; by the
        # time thread 2 is unblocked, thread 1's entire transaction has committed,
        # and the subsequent TokenLoginLog SELECT runs as a fresh READ COMMITTED
        # statement that sees thread 1's new row.
        User.objects.select_for_update().get(pk=user.pk)

        active_sessions = list(
            TokenLoginLog.objects
            .filter(user=user, status=TokenLoginLog.LOGIN, logout_at__isnull=True)
            .order_by('login_at')
        )

        if len(active_sessions) >= max_sessions:
            oldest = active_sessions[0]
            outstanding = OutstandingToken.objects.filter(jti=oldest.jti).first()
            if outstanding:
                BlacklistedToken.objects.get_or_create(token=outstanding)
            oldest.status = TokenLoginLog.REVOKED
            oldest.logout_at = timezone.now()
            oldest.save(update_fields=['status', 'logout_at'])

        TokenLoginLog.objects.create(
            user=user,
            status=TokenLoginLog.LOGIN,
            expires_at=timezone.now() + api_settings.REFRESH_TOKEN_LIFETIME,
            jti=new_jti,
        )


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
            jti = str(token.get('jti'))
            
            # Marcar en TokenLoginLog como logout
            TokenLoginLog.objects.filter(jti=jti).update(
                   status=TokenLoginLog.LOGOUT,
                   logout_at=timezone.now()
            )
            
            # Blacklist el token
            token.blacklist()
        except Exception:
            raise serializers.ValidationError({"refresh": "Token invàlid o ja invalidat."})


class MeSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    is_system_admin = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "role",
            "is_staff",
            "is_superuser",
            "is_system_admin",
        )

    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return profile.role
        return None

    def get_is_system_admin(self, obj):
        return bool(obj.is_superuser)


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
        fields = ("email", "first_name", "last_name")
        extra_kwargs = {
            "email": {"required": False},
            "first_name": {"required": False, "allow_blank": True},
            "last_name": {"required": False, "allow_blank": True},
        }

    def validate_email(self, value):
        value = value.strip().lower()

        if User.objects.exclude(pk=self.instance.pk).filter(email=value).exists():
            raise serializers.ValidationError(
                "Ja existeix un usuari amb aquest correu electrònic."
            )

        return value

    def update(self, instance, validated_data):
        update_fields = []

        if "email" in validated_data:
            instance.email = validated_data["email"]
            update_fields.append("email")

        if "first_name" in validated_data:
            instance.first_name = validated_data["first_name"]
            update_fields.append("first_name")

        if "last_name" in validated_data:
            instance.last_name = validated_data["last_name"]
            update_fields.append("last_name")

        if update_fields:
            try:
                instance.save(update_fields=update_fields)
            except IntegrityError:
                # Race condition: otro hilo grabó el mismo email entre el
                # validate_email y este save. Constraint UNIQUE → 400, no 500.
                raise serializers.ValidationError(
                    {"email": "Ja existeix un usuari amb aquest correu electrònic."}
                )

        return instance

class RoleUpdateSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=RoleChoices.choices)

    def validate_role(self, value):
        allowed_roles = {RoleChoices.OWNER, RoleChoices.TENANT}
        if value not in allowed_roles:
            raise serializers.ValidationError(
                "Només es permet canviar entre els rols owner i tenant."
            )
        return value

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def save(self, **kwargs):
        email = self.validated_data["email"].strip().lower()
        user = User.objects.filter(email=email, is_active=True).first()

        # No enumeració de comptes: si no existeix, no retornem error.
        if not user:
            return {}

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        # MVP: retornem uid/token perquè el frontend pugui construir el flux.
        # En producció això s'enviaria per email.
        return {
            "uid": uid,
            "token": token,
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Les contrasenyes no coincideixen."}
            )

        try:
            user_id = urlsafe_base64_decode(attrs["uid"]).decode()
            user = User.objects.get(pk=user_id, is_active=True)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"token": "Token invàlid o expirat."})

        if not default_token_generator.check_token(user, attrs["token"]):
            raise serializers.ValidationError({"token": "Token invàlid o expirat."})

        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)})

        attrs["user"] = user
        return attrs

    def save(self, **kwargs):
        user = self.validated_data["user"]
        user.set_password(self.validated_data["password"])
        user.save(update_fields=["password"])
        return user
