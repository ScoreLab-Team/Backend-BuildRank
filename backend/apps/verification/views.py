# apps/verification/views.py
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminSistema, IsAdminFinca

from .models import AdminFincaDocumentVerification
from .serializers import (
    AdminFincaDocumentVerificationCreateSerializer,
    AdminFincaDocumentVerificationSerializer,
)
from .services.review import aprovar_verificacio, rebutjar_verificacio


class AdminFincaDocumentVerificationCreateView(generics.CreateAPIView):
    """
    POST /api/verification/create/
    Crea una nova verificació amb un o més documents adjunts.
    """
    serializer_class = AdminFincaDocumentVerificationCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminFinca]
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = serializer.save()

        from .tasks import process_verification
        task = process_verification.delay(verification.pk)
        verification.celery_task_id = task.id
        verification.save(update_fields=['celery_task_id'])

        output = AdminFincaDocumentVerificationSerializer(
            verification, context={'request': request}
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class AdminFincaDocumentVerificationListView(generics.ListAPIView):
    """
    GET /api/verification/
    Llista verificacions. AdminSistema veu totes; usuari normal les seves.
    """
    serializer_class = AdminFincaDocumentVerificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminFinca]

    def get_queryset(self):
        qs = AdminFincaDocumentVerification.objects.select_related(
            'result'
        ).prefetch_related('documents')
        if IsAdminSistema().has_permission(self.request, self):
            return qs
        return qs.filter(user=self.request.user)


class AdminFincaDocumentVerificationDetailView(generics.RetrieveAPIView):
    """
    GET /api/verification/<id>/
    Detall d'una verificació.
    """
    serializer_class = AdminFincaDocumentVerificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdminFinca]

    def get_queryset(self):
        qs = AdminFincaDocumentVerification.objects.select_related(
            'result'
        ).prefetch_related('documents')
        if IsAdminSistema().has_permission(self.request, self):
            return qs
        return qs.filter(user=self.request.user)


class VerificacioRevisioView(APIView):
    """
    POST /api/verification/<id>/revisar/

    Endpoint exclusiu per a superusuaris.
    Aprova o rebutja una verificació en estat 'review'.

    Body:
        {
            "accio": "aprovar" | "rebutjar",
            "motiu": "text opcional — requerit si rebutja"
        }

    Respostes:
        200 → decisió aplicada correctament
        400 → accio invàlida o motiu absent en rebuig
        403 → no és superusuari
        404 → verificació no trobada
        409 → verificació no està en estat 'review'
    """
    permission_classes = [permissions.IsAuthenticated, IsAdminSistema]

    def post(self, request, pk):
        # Carrega la verificació
        try:
            verification = AdminFincaDocumentVerification.objects.select_related(
                'user', 'user__profile', 'edifici'
            ).prefetch_related('documents').get(pk=pk)
        except AdminFincaDocumentVerification.DoesNotExist:
            return Response(
                {'detail': 'Verificació no trobada.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Només es pot revisar si està en estat 'review'
        if verification.status != AdminFincaDocumentVerification.Status.REVIEW:
            return Response(
                {
                    'detail': f"La verificació no es pot revisar en estat '{verification.status}'.",
                    'status_actual': verification.status,
                },
                status=status.HTTP_409_CONFLICT,
            )

        accio = request.data.get('accio', '').strip().lower()
        motiu = request.data.get('motiu', '').strip()

        if accio not in ('aprovar', 'rebutjar'):
            return Response(
                {'detail': "El camp 'accio' ha de ser 'aprovar' o 'rebutjar'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if accio == 'rebutjar' and not motiu:
            return Response(
                {'detail': "Cal indicar un 'motiu' quan es rebutja una verificació."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Executa la decisió
        if accio == 'aprovar':
            aprovar_verificacio(verification, reviewer=request.user)
            return Response({
                'detail': f"Verificació #{pk} aprovada.",
                'edifici': verification.edifici.pk,
                'administrador_assignat': verification.user.email,
            })
        else:
            rebutjar_verificacio(verification, reviewer=request.user, motiu=motiu)
            return Response({
                'detail': f"Verificació #{pk} rebutjada.",
                'motiu': motiu,
            })