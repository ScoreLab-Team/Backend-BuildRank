# apps/buildings/urls.py
from rest_framework.routers import DefaultRouter
from .views import EdificiViewSet, HabitatgeViewSet, LocalitzacioViewSet, DadesEnergetiquesViewSet

router = DefaultRouter()
router.register(r'edificis', EdificiViewSet, basename='edifici')
router.register(r'habitatges', HabitatgeViewSet, basename='habitatge')
router.register(r'localitzacions', LocalitzacioViewSet, basename='localizacio')
router.register(r'dades_energetiques', DadesEnergetiquesViewSet, basename='dades-energetiques')

urlpatterns = router.urls