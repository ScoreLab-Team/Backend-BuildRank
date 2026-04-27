from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView as SimpleJWTTokenRefreshView

from apps.accounts.models import RoleChoices
from apps.buildings.models import Edifici, Habitatge
from apps.accounts.permissions import IsAdminSistema, IsAdminFinca, ABACMixin
from apps.accounts.throttles import LoginThrottle, RegisterThrottle, RefreshThrottle
from apps.accounts.serializers import (
    RegisterSerializer, LoginSerializer, LogoutSerializer, MeSerializer,
    AccountUpdateSerializer, RoleUpdateSerializer,
    EdificiResumSerializer, HabitatgeResumSerializer,
    AssignarResidentSerializer, AssignarAdminSerializer,
)

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
            # Admin de finca: edificis de la seva cartera
            edificis = user.edificis_administrats.select_related("localitzacio").all()
        else:
            # Owner / Tenant: edificis on té vinculació per habitatge
            edificis = (
                Edifici.objects.select_related("localitzacio")
                .filter(habitatges__usuari=user)
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