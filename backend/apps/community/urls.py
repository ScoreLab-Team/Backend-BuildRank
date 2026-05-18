from django.urls import path
from .views import (
    VotacioListCreateView,
    VotacioDetailView,
    EmitreVotView,
    ResultatsVotacioView,
)

urlpatterns = [
    path('votacions/', VotacioListCreateView.as_view(), name='votacio-list-create'),
    path('votacions/<int:pk>/', VotacioDetailView.as_view(), name='votacio-detail'),
    path('votacions/<int:pk>/votar/', EmitreVotView.as_view(), name='votacio-votar'),
    path('votacions/<int:pk>/resultats/', ResultatsVotacioView.as_view(), name='votacio-resultats'),
]
