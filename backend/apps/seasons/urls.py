from rest_framework.routers import DefaultRouter
from .views import TemporadaViewSet

router = DefaultRouter()
router.register(r'', TemporadaViewSet, basename='temporada')

urlpatterns = router.urls