from django.urls import path

from apps.accounts.views import (
    RegisterView, LoginView, TokenRefreshView, LogoutView, MeView, MeRoleView,
    MeEdificisView, AssignarResidentView, AssignarAdminEdificiView,
)

urlpatterns = [
    # Auth
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/role/", MeRoleView.as_view(), name="me-role"),

    # Consulta: edificis accessibles per l'usuari autenticat
    path("me/edificis/", MeEdificisView.as_view(), name="me-edificis"),

    # Assignació: resident → habitatge (AdminFinca, ABAC-B)
    path(
        "habitatges/<str:ref_cadastral>/assignar-resident/",
        AssignarResidentView.as_view(),
        name="assignar-resident",
    ),

    # Assignació: admin → edifici (AdminSistema only)
    path(
        "edificis/<int:id_edifici>/assignar-admin/",
        AssignarAdminEdificiView.as_view(),
        name="assignar-admin-edifici",
    ),
]