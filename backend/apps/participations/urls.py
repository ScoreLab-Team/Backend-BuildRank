from rest_framework.routers import DefaultRouter
from .views import ParticipacioViewSet

router = DefaultRouter()
router.register(r'', ParticipacioViewSet, basename='participacio')

urlpatterns = router.urls