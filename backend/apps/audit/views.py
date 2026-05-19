from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination

from apps.accounts.permissions import IsAdminSistema

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200


class AuditLogListView(ListAPIView):
    """
    GET /api/audit/logs/

    Paràmetres de filtratge (query params):
      - user_id       : filtra per usuari
      - method        : GET, POST, PUT, PATCH, DELETE
      - resource_type : buildings, accounts, verification...
      - status_code   : codi de resposta HTTP
      - from_date     : ISO 8601, ex. 2026-05-01
      - to_date       : ISO 8601, ex. 2026-05-31
    """
    permission_classes = [IsAdminSistema]
    serializer_class = AuditLogSerializer
    pagination_class = AuditLogPagination

    def get_queryset(self):
        qs = AuditLog.objects.select_related('user').all()

        params = self.request.query_params

        if user_id := params.get('user_id'):
            qs = qs.filter(user_id=user_id)

        if method := params.get('method'):
            qs = qs.filter(method=method.upper())

        if resource_type := params.get('resource_type'):
            qs = qs.filter(resource_type=resource_type)

        if status_code := params.get('status_code'):
            qs = qs.filter(status_code=status_code)

        if from_date := params.get('from_date'):
            qs = qs.filter(timestamp__date__gte=from_date)

        if to_date := params.get('to_date'):
            qs = qs.filter(timestamp__date__lte=to_date)

        return qs
