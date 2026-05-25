from django.urls import path

from .views import (
    AdminFincaDocumentVerificationCreateView,
    AdminFincaDocumentVerificationDetailView,
    AdminFincaDocumentVerificationListView,
    VerificacioRevisioView,
)

app_name = 'verification'

urlpatterns = [
   path('',AdminFincaDocumentVerificationListView.as_view(),name='list',),
   path('create/',AdminFincaDocumentVerificationCreateView.as_view(),name='create',),
   path('<int:pk>/',AdminFincaDocumentVerificationDetailView.as_view(),name='detail',),
   path('<int:pk>/revisar/', VerificacioRevisioView.as_view(),name='revisar'),
]