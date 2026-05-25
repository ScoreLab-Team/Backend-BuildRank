from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from rest_framework import serializers

from apps.accounts.models import AccountStatus, Profile, RoleChoices, TokenLoginLog
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

from django.conf import settings
from django.core.mail import send_mail
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from google.auth.exceptions import GoogleAuthError

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

        user_obj = User.objects.filter(email=email).first()

        if (
            user_obj is not None
            and user_obj.auth_provider == User.AuthProvider.GOOGLE
        ):
            raise serializers.ValidationError(
                "Aquest compte es va crear amb Google. Inicia sessió amb Google."
            )

        user = authenticate(username=email, password=password)

        if not user:
            raise serializers.ValidationError("Credencials invàlides.")

        if not user.is_active:
            raise serializers.ValidationError("Aquest usuari està inactiu.")

        profile = getattr(user, "profile", None)
        if profile is not None:
            if profile.account_status == AccountStatus.BLOCKED:
                raise serializers.ValidationError(
                    "Aquest compte ha estat bloquejat. Contacteu amb l'administrador."
                )
            if profile.account_status == AccountStatus.SUSPENDED:
                from django.utils import timezone as tz
                until = profile.suspended_until
                if until is None or until > tz.now():
                    raise serializers.ValidationError(
                        "Aquest compte està suspès temporalment."
                    )
                # Suspension expired — auto-lift so the DB reflects reality.
                profile.account_status = AccountStatus.ACTIVE
                profile.suspension_reason = ""
                profile.suspended_until = None
                profile.save(update_fields=["account_status", "suspension_reason", "suspended_until"])

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
    account_status = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

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
            "account_status",
            "avatar_url",
        )

    def get_role(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return profile.role
        return None

    def get_is_system_admin(self, obj):
        return bool(obj.is_superuser)

    def get_account_status(self, obj):
        profile = getattr(obj, "profile", None)
        if profile:
            return profile.account_status
        return AccountStatus.ACTIVE

    def get_avatar_url(self, obj):
        profile = getattr(obj, "profile", None)
        if not profile or not profile.avatar:
            return None

        request = self.context.get("request")
        url = profile.avatar.url

        if request is not None:
            return request.build_absolute_uri(url)

        return url


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
    avatar = serializers.ImageField(required=False, allow_null=True)
    avatar_clear = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "avatar", "avatar_clear")
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

    def validate_avatar(self, value):
        if value is None:
            return value

        max_size = 2 * 1024 * 1024
        if value.size > max_size:
            raise serializers.ValidationError(
                "L'avatar no pot superar els 2 MB."
            )

        allowed_content_types = {
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/gif",
        }
        content_type = getattr(value, "content_type", "")

        if content_type and content_type not in allowed_content_types:
            raise serializers.ValidationError(
                "Format d'imatge no permès. Usa JPG, PNG, WEBP o GIF."
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

        avatar_clear = validated_data.pop("avatar_clear", False)
        avatar_provided = "avatar" in validated_data

        if avatar_provided or avatar_clear:
            try:
                profile = instance.profile
            except Profile.DoesNotExist:
                profile = Profile.objects.create(user=instance)

            old_avatar_name = profile.avatar.name if profile.avatar else None
            new_avatar = validated_data.get("avatar") if avatar_provided else None

            if old_avatar_name:
                profile.avatar.delete(save=False)

            if avatar_clear and not avatar_provided:
                profile.avatar = None
            elif avatar_provided:
                profile.avatar = new_avatar

            profile.save(update_fields=["avatar", "updated_at"])
            instance._state.fields_cache["profile"] = profile

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

        # No enumeració de comptes: si no existeix, no retornem error ni enviem res.
        if not user:
            return {}

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)

        reset_base_url = getattr(
            settings,
            "PASSWORD_RESET_FRONTEND_URL",
            "http://localhost:3000/reset-password",
        )
        reset_url = f"{reset_base_url}?uid={uid}&token={token}"

        message = (
            "Has sol·licitat restablir la contrasenya del teu compte de BuildRank.\n\n"
            f"Obre aquest enllaç per crear una contrasenya nova:\n{reset_url}\n\n"
            "Si no has sol·licitat aquest canvi, pots ignorar aquest missatge."
        )

        send_mail(
            subject="Restabliment de contrasenya de BuildRank",
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@buildrank.local"),
            recipient_list=[user.email],
            fail_silently=True,
        )

        # Important: no retornem uid/token a l'API. Només viatgen per email.
        return {}


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

        # Revocar refresh tokens actius després del canvi de contrasenya.
        # Els access tokens ja emesos poden continuar fins a expirar, però no es podrà renovar sessió.
        now = timezone.now()
        for outstanding in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=outstanding)

        TokenLoginLog.objects.filter(
            user=user,
            status=TokenLoginLog.LOGIN,
            logout_at__isnull=True,
        ).update(
            status=TokenLoginLog.REVOKED,
            logout_at=now,
        )

        return user


# ---------------------------------------------------------------------------
# Gestió d'usuaris (US49) — només AdminSistema
# ---------------------------------------------------------------------------

class UserAdminSerializer(serializers.ModelSerializer):
    """Representació completa d'un usuari per al panell d'administració."""
    role = serializers.CharField(source="profile.role", read_only=True)
    account_status = serializers.CharField(source="profile.account_status", read_only=True)
    suspension_reason = serializers.CharField(source="profile.suspension_reason", read_only=True)
    suspended_until = serializers.DateTimeField(source="profile.suspended_until", read_only=True)

    class Meta:
        model = User
        fields = (
            "id",
            "email",
            "first_name",
            "last_name",
            "is_active",
            "is_superuser",
            "date_joined",
            "role",
            "account_status",
            "suspension_reason",
            "suspended_until",
        )


class SuspendSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)
    suspended_until = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Null o omès = suspensió indefinida.",
    )


class GoogleOAuthSerializer(serializers.Serializer):
    id_token = serializers.CharField(write_only=True)
    mode = serializers.ChoiceField(
        choices=["login", "register"],
        write_only=True,
    )
    role = serializers.ChoiceField(choices=RoleChoices.choices, required=False)

    def validate(self, attrs):
        token = attrs["id_token"]

        if not settings.GOOGLE_OAUTH_CLIENT_ID:
            raise serializers.ValidationError(
                {"detail": "GOOGLE_OAUTH_CLIENT_ID no està configurat."}
            )

        try:
            idinfo = google_id_token.verify_oauth2_token(
                token,
                google_requests.Request(),
                settings.GOOGLE_OAUTH_CLIENT_ID,
            )
        except ValueError:
            raise serializers.ValidationError({"id_token": "Token de Google invàlid."})
        except GoogleAuthError:
            raise serializers.ValidationError(
                {"id_token": "No s'ha pogut verificar el token de Google."}
            )

        email = (idinfo.get("email") or "").strip().lower()
        if not email:
            raise serializers.ValidationError({"email": "Google no ha retornat cap email."})

        if not idinfo.get("email_verified", False):
            raise serializers.ValidationError({"email": "L'email de Google no està verificat."})

        attrs["google_user_info"] = {
            "email": email,
            "first_name": idinfo.get("given_name", "") or "",
            "last_name": idinfo.get("family_name", "") or "",
        }
        return attrs

    @transaction.atomic
    def save(self, **kwargs):
        info = self.validated_data["google_user_info"]
        mode = self.validated_data["mode"]

        user = User.objects.filter(email=info["email"]).first()

        if mode == "register":
            if user is not None:
                raise serializers.ValidationError(
                    {
                        "detail": "Aquest email ja té un compte. Inicia sessió amb el mètode utilitzat en el registre."
                    }
                )

            user = User.objects.create_user(
                email=info["email"],
                first_name=info["first_name"],
                last_name=info["last_name"],
                password=None,
                auth_provider=User.AuthProvider.GOOGLE,
                is_active=True,
            )

            profile, _ = Profile.objects.get_or_create(user=user)
            profile.role = self.validated_data.get("role", RoleChoices.OWNER)
            profile.save(update_fields=["role"])

        elif mode == "login":
            if user is None:
                raise serializers.ValidationError(
                    {"detail": "No existeix cap compte amb aquest Google. Registra’t primer."}
                )

            if user.auth_provider != User.AuthProvider.GOOGLE:
                raise serializers.ValidationError(
                    {
                        "detail": "Aquest compte es va crear amb email i contrasenya. Inicia sessió amb la contrasenya de BuildRank."
                    }
                )

            profile, _ = Profile.objects.get_or_create(user=user)

        else:
            raise serializers.ValidationError({"mode": "Mode OAuth invàlid."})

        user.profile.refresh_from_db()

        if profile.account_status == AccountStatus.BLOCKED:
            raise serializers.ValidationError(
                "Aquest compte ha estat bloquejat. Contacteu amb l'administrador."
            )
        if profile.account_status == AccountStatus.SUSPENDED:
            from django.utils import timezone as tz
            until = profile.suspended_until
            if until is None or until > tz.now():
                raise serializers.ValidationError(
                    "Aquest compte està suspès temporalment."
                )
            # Suspension expired — auto-lift so the DB reflects reality.
            profile.account_status = AccountStatus.ACTIVE
            profile.suspension_reason = ""
            profile.suspended_until = None
            profile.save(update_fields=["account_status", "suspension_reason", "suspended_until"])

        refresh = RefreshToken.for_user(user)
        jti = str(refresh.get("jti"))

        TokenLoginLog.objects.create(
            user=user,
            status=TokenLoginLog.LOGIN,
            expires_at=timezone.now() + api_settings.REFRESH_TOKEN_LIFETIME,
            jti=jti,
        )

        return {
            "user": user,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }
