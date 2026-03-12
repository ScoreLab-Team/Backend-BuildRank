# apps/buildings/urls.py
from rest_framework.routers import DefaultRouter
from .views import EdificiViewSet, HabitatgeViewSet, LocalitzacioViewSet, DadesEnergetiquesViewSet

router = DefaultRouter()
router.register(r'edificis', EdificiViewSet)
router.register(r'habitatges', HabitatgeViewSet)
router.register(r'localitzacions', LocalitzacioViewSet)
router.register(r'dades_energetiques', DadesEnergetiquesViewSet)

urlpatterns = router.urls