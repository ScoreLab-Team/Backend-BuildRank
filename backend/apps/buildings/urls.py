# apps/buildings/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    EdificiViewSet,
    EdificisMostrarAPIView,
    EdificiVeureAPIView,
    EdificiEditarAPIView,
    EdificiCrearAPIView,
    EdificiEsborrarAPIView,
    HabitatgeViewSet,
    LocalitzacioViewSet,
    DadesEnergetiquesViewSet,
    autocomplete_carrers,
    RankingViewSet,
    CatalegMilloraViewSet,
    MilloraImplementadaViewSet,
    AdminFincaEdificiAltaView,
)

router = DefaultRouter()
router.register(r'edificis', EdificiViewSet, basename='edifici')
router.register(r'habitatges', HabitatgeViewSet, basename='habitatge')
router.register(r'localitzacions', LocalitzacioViewSet, basename='localitzacio')
router.register(r'dades_energetiques', DadesEnergetiquesViewSet, basename='dades-energetiques')
router.register(r'ranking', RankingViewSet, basename='ranking')
router.register(r'millores', CatalegMilloraViewSet, basename='millora')
router.register(r'millores-implementades', MilloraImplementadaViewSet, basename='millora-implementada')

# urlpatterns = router.urls

urlpatterns = [
    path('admin-finca/edificis/alta/', AdminFincaEdificiAltaView.as_view(), name='admin-finca-edifici-alta'),
    # Rutes manuals APIView (compatibilitat), amb noms no col·lisionants amb el router
    path('edificis/manual/', EdificisMostrarAPIView.as_view(), name='edifici-list-manual'),
    path('edificis/manual/<str:pk>/', EdificiVeureAPIView.as_view(), name='edifici-detail-manual'),
    path('carrers/autocomplete/', autocomplete_carrers, name='autocomplete-carrers'),
    # Afegim tota la resta de rutes automàtiques del router
    path('', include(router.urls)),
]