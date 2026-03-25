# apps/buildings/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (EdificiVeureAPIView, EdificiEditarAPIView, 
    EdificisMostrarAPIView, EdificiCrearAPIView, EdificiEsborrarAPIView,
    HabitatgeViewSet, LocalitzacioViewSet, DadesEnergetiquesViewSet, autocomplete_carrers,
    EdificiDetailAPIView, EdificiViewSet, EdificiListAPIView
)

router = DefaultRouter()
router.register(r'edificis', EdificiViewSet, basename='edifici')
router.register(r'habitatges', HabitatgeViewSet, basename='habitatge')
router.register(r'localitzacions', LocalitzacioViewSet, basename='localitzacio')
router.register(r'dades_energetiques', DadesEnergetiquesViewSet, basename='dades-energetiques')

# urlpatterns = router.urls

urlpatterns = [
    # get de tots els edificis
    path('edificis/mostrar/', EdificisMostrarAPIView.as_view(), name='edifici-mostrar'),
    # post un edifici
    path('edificis/crear/', EdificiCrearAPIView.as_view(), name='edifici-crear'),
    # get un edifici concret
    path('edificis/<int:pk>/veure/', EdificiVeureAPIView.as_view(), name='edifici-veure'),
    # patch i put d'un edifici concret
    path('edificis/<int:pk>/editar/', EdificiEditarAPIView.as_view(), name='edifici-editar'),
    # delete un edifici
    path('edificis/<int:pk>/esborrar/', EdificiEsborrarAPIView.as_view(), name='edifici-esborrar'),

    path('carrers/autocomplete/', autocomplete_carrers, name='autocomplete-carrers'),
    path('carrers/autocomplete/', autocomplete_carrers, name='autocomplete-carrers'),
    # Afegim tota la resta de rutes automàtiques del router
    path('', include(router.urls)),
]