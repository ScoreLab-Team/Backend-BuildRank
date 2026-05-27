from rest_framework.routers import DefaultRouter
from .views import LligaViewSet

router = DefaultRouter()
router.register(r'', LligaViewSet, basename='lliga')

urlpatterns = router.urls