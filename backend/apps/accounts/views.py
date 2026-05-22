from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken, BlacklistedToken

from apps.accounts.models import AccountStatus, RoleChoices, TokenLoginLog
from apps.buildings.models import Edifici, Habitatge
from apps.accounts.permissions import IsAdminSistema, IsAdminFinca, ABACMixin
from apps.accounts.throttles import LoginThrottle, RegisterThrottle, RefreshThrottle
from apps.accounts.serializers import (
    RegisterSerializer, LoginSerializer, LogoutSerializer, MeSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    AccountUpdateSerializer, RoleUpdateSerializer,
    EdificiResumSerializer, HabitatgeResumSerializer,
    AssignarResidentSerializer, AssignarAdminSerializer,
    GoogleOAuthSerializer,
    UserAdminSerializer, SuspendSerializer,
)

User = get_user_model()

class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                "id": user.id,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": user.profile.role,
            },
            status=status.HTTP_201_CREATED,
        )

class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        user = data["user"]

        return Response(
            {
                "access": data["access"],
                "refresh": data["refresh"],
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.profile.role,
                }
            },
            status=status.HTTP_200_OK,
        )


class GoogleOAuthView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = GoogleOAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        user = data["user"]

        return Response(
            {
                "access": data["access"],
                "refresh": data["refresh"],
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "role": user.profile.role,
                },
            },
            status=status.HTTP_200_OK,
        )


class TokenRefreshView(SimpleJWTTokenRefreshView):
    throttle_classes = [RefreshThrottle]


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Sessió tancada correctament."},
            status=status.HTTP_200_OK,
        )

class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {
                "detail": "Si el correu existeix, s'han enviat instruccions per restablir la contrasenya."
            },
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"detail": "Contrasenya restablerta correctament."},
            status=status.HTTP_200_OK,
        )

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = AccountUpdateSerializer(request.user, data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MeSerializer(user).data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = AccountUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(MeSerializer(user).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Consulta: a quins edificis pot accedir l'usuari autenticat
# ---------------------------------------------------------------------------

class MeEdificisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = getattr(getattr(user, "profile", None), "role", None)

        if user.is_superuser:
            edificis = Edifici.objects.select_related("localitzacio").all()
        elif role == RoleChoices.ADMIN:
            # Admin de finca: només edificis amb assignació efectiva.
            # Si hi ha verificació documental per aquest edifici, ha d'estar approved.
            from apps.verification.access import effective_admin_buildings_queryset

            edificis = effective_admin_buildings_queryset(
                Edifici.objects.select_related("localitzacio"),
                user,
            )
        else:
            # Owner / Tenant: edificis on té vinculació per habitatge
            edificis = (
                Edifici.objects.select_related("localitzacio")
                .filter(
                    Q(habitatges__usuari=user)
                    | Q(habitatges__propietari=user)
                    | Q(habitatges__llogater=user)
                )
                .distinct()
            )

        serializer = EdificiResumSerializer(edificis, many=True)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Assignació: resident → habitatge  (AdminFinca, ABAC-B)
# ---------------------------------------------------------------------------

class AssignarResidentView(ABACMixin, APIView):
    permission_classes = [IsAdminFinca]

    def patch(self, request, ref_cadastral):
        try:
            habitatge = Habitatge.objects.select_related('edifici').get(
                referenciaCadastral=ref_cadastral
            )
        except Habitatge.DoesNotExist:
            return Response({"detail": "Habitatge no trobat."}, status=status.HTTP_404_NOT_FOUND)

        # ABAC-B: l'edifici ha d'estar a la cartera de l'admin
        self.check_edifici_access(request, habitatge.edifici.idEdifici)

        serializer = AssignarResidentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        habitatge.usuari_id = user_id
        habitatge.save(update_fields=['usuari_id'])

        return Response(HabitatgeResumSerializer(habitatge).data)


# ---------------------------------------------------------------------------
# Assignació: admin → edifici  (només AdminSistema)
# ---------------------------------------------------------------------------

class AssignarAdminEdificiView(APIView):
    permission_classes = [IsAdminSistema]

    def patch(self, request, id_edifici):
        try:
            edifici = Edifici.objects.get(idEdifici=id_edifici)
        except Edifici.DoesNotExist:
            return Response({"detail": "Edifici no trobat."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssignarAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        edifici.administradorFinca_id = user_id
        edifici.save(update_fields=['administradorFinca_id'])

        return Response(EdificiResumSerializer(edifici).data)

# ---------------------------------------------------------------------------
# Canvi de rol (US5)
# ---------------------------------------------------------------------------

class MeRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = RoleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = request.user.profile
        new_role = serializer.validated_data["role"]

        profile.role = new_role
        profile.save(update_fields=["role", "updated_at"])

        return Response(
            MeSerializer(request.user).data,
            status=status.HTTP_200_OK
        )


# ---------------------------------------------------------------------------
# Gestió d'usuaris (US49) — només AdminSistema
# ---------------------------------------------------------------------------

def _revoke_all_user_tokens(user):
    """Blacklist every outstanding refresh token and mark all active sessions as REVOKED."""
    outstanding = OutstandingToken.objects.filter(user=user)
    for token in outstanding:
        BlacklistedToken.objects.get_or_create(token=token)

    TokenLoginLog.objects.filter(
        user=user,
        status=TokenLoginLog.LOGIN,
        logout_at__isnull=True,
    ).update(status=TokenLoginLog.REVOKED, logout_at=timezone.now())


class UserListView(generics.ListAPIView):
    """Llista tots els usuaris de la plataforma."""
    permission_classes = [IsAdminSistema]
    serializer_class = UserAdminSerializer
    queryset = User.objects.select_related("profile").order_by("id")


class UserDetailView(generics.RetrieveAPIView):
    """Detall d'un usuari concret."""
    permission_classes = [IsAdminSistema]
    serializer_class = UserAdminSerializer
    queryset = User.objects.select_related("profile")


class UserBlockView(APIView):
    """
    Bloqueja permanentment un compte.
    Revoca immediatament totes les sessions actives de l'usuari.
    """
    permission_classes = [IsAdminSistema]

    def post(self, request, pk):
        try:
            user = User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Usuari no trobat."}, status=status.HTTP_404_NOT_FOUND)

        if user.is_superuser:
            return Response(
                {"detail": "No es pot bloquejar un administrador del sistema."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            profile = user.profile
            profile.account_status = AccountStatus.BLOCKED
            profile.suspension_reason = ""
            profile.suspended_until = None
            profile.save(update_fields=["account_status", "suspension_reason", "suspended_until", "updated_at"])
            _revoke_all_user_tokens(user)

        return Response(UserAdminSerializer(user).data, status=status.HTTP_200_OK)


class UserUnblockView(APIView):
    """Desbloqueja un compte i el torna a l'estat actiu."""
    permission_classes = [IsAdminSistema]

    def post(self, request, pk):
        try:
            user = User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Usuari no trobat."}, status=status.HTTP_404_NOT_FOUND)

        profile = user.profile
        if profile.account_status != AccountStatus.BLOCKED:
            return Response(
                {"detail": "El compte no està bloquejat."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.account_status = AccountStatus.ACTIVE
        profile.save(update_fields=["account_status", "updated_at"])

        return Response(UserAdminSerializer(user).data, status=status.HTTP_200_OK)


class UserSuspendView(APIView):
    """
    Suspèn temporalment un compte.
    Camps opcionals: reason (text), suspended_until (datetime; null = indefinit).
    Revoca immediatament totes les sessions actives.
    """
    permission_classes = [IsAdminSistema]

    def post(self, request, pk):
        try:
            user = User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Usuari no trobat."}, status=status.HTTP_404_NOT_FOUND)

        if user.is_superuser:
            return Response(
                {"detail": "No es pot suspendre un administrador del sistema."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = SuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            profile = user.profile
            profile.account_status = AccountStatus.SUSPENDED
            profile.suspension_reason = serializer.validated_data.get("reason", "")
            profile.suspended_until = serializer.validated_data.get("suspended_until")
            profile.save(update_fields=["account_status", "suspension_reason", "suspended_until", "updated_at"])
            _revoke_all_user_tokens(user)

        return Response(UserAdminSerializer(user).data, status=status.HTTP_200_OK)


class UserUnsuspendView(APIView):
    """Aixeca la suspensió d'un compte i el torna a l'estat actiu."""
    permission_classes = [IsAdminSistema]

    def post(self, request, pk):
        try:
            user = User.objects.select_related("profile").get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "Usuari no trobat."}, status=status.HTTP_404_NOT_FOUND)

        profile = user.profile
        if profile.account_status != AccountStatus.SUSPENDED:
            return Response(
                {"detail": "El compte no està suspès."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profile.account_status = AccountStatus.ACTIVE
        profile.suspension_reason = ""
        profile.suspended_until = None
        profile.save(update_fields=["account_status", "suspension_reason", "suspended_until", "updated_at"])

        return Response(UserAdminSerializer(user).data, status=status.HTTP_200_OK)


class AdminDashboardSummaryView(APIView):
    """Mètriques agregades per al panell d'administració del sistema."""
    permission_classes = [IsAdminSistema]

    def get(self, request):
        from apps.buildings.models import (
            Edifici,
            Habitatge,
            MilloraImplementada,
            EstatValidacio,
        )
        from apps.verification.models import AdminFincaDocumentVerification
        from apps.seasons.models import Temporada, EstatTemporada

        temporada_activa = (
            Temporada.objects
            .filter(estat=EstatTemporada.ACTIVA)
            .order_by("-dataInici", "-id_temporada")
            .first()
        )

        pending_improvements = MilloraImplementada.objects.filter(
            estatValidacio__in=[
                EstatValidacio.PENDENT_DOCUMENTACIO,
                EstatValidacio.EN_REVISIO,
            ]
        ).count()

        pending_admin_verifications = AdminFincaDocumentVerification.objects.filter(
            status__in=[
                AdminFincaDocumentVerification.Status.PENDING,
                AdminFincaDocumentVerification.Status.RUNNING,
                AdminFincaDocumentVerification.Status.REVIEW,
            ]
        ).count()

        pending_housing_requests = Habitatge.objects.filter(
            estatValidacio__in=[
                EstatValidacio.PENDENT_DOCUMENTACIO,
                EstatValidacio.EN_REVISIO,
            ],
            solicitant__isnull=False,
        ).count()

        active_season = None
        if temporada_activa:
            active_season = {
                "id": temporada_activa.id_temporada,
                "nom": temporada_activa.nom,
                "dataInici": temporada_activa.dataInici,
                "dataFi": temporada_activa.dataFi,
                "estat": temporada_activa.estat,
            }

        return Response(
            {
                "users_total": User.objects.count(),
                "buildings_total": Edifici.actius.count(),
                "buildings_managed": Edifici.actius.filter(
                    administradorFinca__isnull=False
                ).count(),
                "pending_improvements": pending_improvements,
                "pending_admin_verifications": pending_admin_verifications,
                "pending_housing_requests": pending_housing_requests,
                "active_season": active_season,
            },
            status=status.HTTP_200_OK,
        )

