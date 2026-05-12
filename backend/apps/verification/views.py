from django.shortcuts import render

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import AdminFincaDocumentVerification
from .serializers import (
    AdminFincaDocumentVerificationCreateSerializer,
    AdminFincaDocumentVerificationSerializer,
)


class AdminFincaDocumentVerificationCreateView(generics.CreateAPIView):
   """
   POST /api/verification/
   Crea una nova verificació amb un o més documents adjunts.
   Requereix autenticació.
   """

   serializer_class = AdminFincaDocumentVerificationCreateSerializer
   permission_classes = [permissions.IsAuthenticated]

   def create(self, request, *args, **kwargs):
      serializer = self.get_serializer(data=request.data)
      serializer.is_valid(raise_exception=True)
      verification = serializer.save()

      # Sprint 2: aquí s'encuarà la tasca Celery
      # from .tasks import process_verification
      # task = process_verification.delay(verification.id)
      # verification.celery_task_id = task.id
      # verification.save(update_fields=['celery_task_id'])

      output = AdminFincaDocumentVerificationSerializer(
         verification, context={'request': request}
      )
      return Response(output.data, status=status.HTTP_201_CREATED)

class AdminFincaDocumentVerificationListView(generics.ListAPIView):
    """
    GET /api/verification/
    Llista totes les verificacions de l'usuari autenticat.
    Staff veu totes.
    """

    serializer_class = AdminFincaDocumentVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = AdminFincaDocumentVerification.objects.select_related(
            'result'
        ).prefetch_related('documents')

        if user.is_staff:
            return qs
        return qs.filter(user=user)


class AdminFincaDocumentVerificationDetailView(generics.RetrieveAPIView):
    """
    GET /api/verification/<id>/
    Retorna l'estat i el resultat d'una verificació.
    Només accessible pel administrador de Finca.
    """

    serializer_class = AdminFincaDocumentVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = AdminFincaDocumentVerification.objects.select_related(
            'result'
        ).prefetch_related('documents')

        if user.is_staff:
            return qs
        return qs.filter(user=user)


