from rest_framework import generics, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Q
from django.shortcuts import get_object_or_404

from apps.buildings.models import Edifici
from .models import Votacio
from .serializers import (
    VotacioCreateSerializer,
    VotacioDetailSerializer,
    VotacioListSerializer,
    VotacioUpdateSerializer,
    EmitreVotSerializer,
    ResultatsVotacioSerializer,
)


def _is_edifici_member(user, edifici):
    if user.is_superuser:
        return True
    if edifici.administradorFinca_id == user.id:
        return True
    return edifici.habitatges.filter(Q(usuari=user) | Q(propietari=user) | Q(llogater=user)).exists()


def _is_edifici_admin(user, edifici):
    return edifici.administradorFinca_id == user.id


def _can_vote(user, edifici):
    if _is_edifici_admin(user, edifici):
        return True
    try:
        if user.profile.role == 'owner':
            return edifici.habitatges.filter(Q(usuari=user) | Q(propietari=user)).exists()
    except Exception:
        pass
    return False


class VotacioListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return VotacioCreateSerializer
        return VotacioListSerializer

    def get_queryset(self):
        edifici_id = self.request.query_params.get('edifici')
        if not edifici_id:
            return Votacio.objects.none()
        edifici = get_object_or_404(Edifici, pk=edifici_id, actiu=True)
        if not _is_edifici_member(self.request.user, edifici):
            return Votacio.objects.none()
        return Votacio.objects.filter(edifici=edifici)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        edifici = serializer.validated_data['edifici']
        if not _is_edifici_admin(request.user, edifici):
            return Response(
                {'detail': "Només l'administrador de finca pot crear votacions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        votacio = serializer.save()
        return Response(
            VotacioDetailSerializer(votacio, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


class VotacioDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method in ('PATCH', 'PUT'):
            return VotacioUpdateSerializer
        return VotacioDetailSerializer

    def get_object(self):
        votacio = get_object_or_404(Votacio, pk=self.kwargs['pk'])
        if not _is_edifici_member(self.request.user, votacio.edifici):
            raise PermissionDenied()
        return votacio

    def _check_admin_finca(self, votacio):
        if not _is_edifici_admin(self.request.user, votacio.edifici):
            raise PermissionDenied("Només l'administrador de finca pot modificar votacions.")

    def update(self, request, *args, **kwargs):
        votacio = self.get_object()
        self._check_admin_finca(votacio)
        serializer = self.get_serializer(votacio, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(VotacioDetailSerializer(votacio, context={'request': request}).data)

    def destroy(self, request, *args, **kwargs):
        votacio = self.get_object()
        self._check_admin_finca(votacio)
        votacio.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmitreVotView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        votacio = get_object_or_404(Votacio, pk=pk)
        if not _can_vote(request.user, votacio.edifici):
            return Response(
                {'detail': "Només poden votar l'administrador de finca i els propietaris del mateix edifici."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = EmitreVotSerializer(
            data=request.data,
            context={'votacio': votacio, 'request': request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'detail': 'Vot registrat correctament.'},
            status=status.HTTP_201_CREATED,
        )


class ResultatsVotacioView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ResultatsVotacioSerializer

    def get_object(self):
        votacio = get_object_or_404(Votacio, pk=self.kwargs['pk'])
        if not _is_edifici_member(self.request.user, votacio.edifici):
            raise PermissionDenied()
        return votacio
