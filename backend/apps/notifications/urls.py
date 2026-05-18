from django.urls import path
from .views import NotificacioListView, NoLlegidesCountView, LlegirNotificacioView, LlegirTotesView

urlpatterns = [
    path('', NotificacioListView.as_view(), name='notificacio-list'),
    path('no-llegides/', NoLlegidesCountView.as_view(), name='notificacio-no-llegides'),
    path('<int:pk>/llegir/', LlegirNotificacioView.as_view(), name='notificacio-llegir'),
    path('llegir-totes/', LlegirTotesView.as_view(), name='notificacio-llegir-totes'),
]
