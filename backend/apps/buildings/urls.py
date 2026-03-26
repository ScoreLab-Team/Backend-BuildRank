# apps/buildings/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EdificiDetailAPIView, EdificiListAPIView, HabitatgeViewSet, LocalitzacioViewSet, DadesEnergetiquesViewSet, RankingViewSet

router = DefaultRouter()
# router.register(r'edificis', EdificiViewSet, basename='edifici')
router.register(r'habitatges', HabitatgeViewSet, basename='habitatge')
router.register(r'localitzacions', LocalitzacioViewSet, basename='localitzacio')
router.register(r'dades_energetiques', DadesEnergetiquesViewSet, basename='dades-energetiques')
router.register(r'ranking', RankingViewSet, basename='ranking')

# urlpatterns = router.urls

urlpatterns = [
    # Rutes manuals per als teus APIView d'Edificis
    path('edificis/', EdificiListAPIView.as_view(), name='edifici-list'),
    path('edificis/<str:pk>/', EdificiDetailAPIView.as_view(), name='edifici-detail'),
    
    # Afegim tota la resta de rutes automàtiques del router
    path('', include(router.urls)),
]