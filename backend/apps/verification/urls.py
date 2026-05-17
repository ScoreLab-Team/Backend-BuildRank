from django.urls import path

from .views import (
    AdminFincaDocumentVerificationCreateView,
    AdminFincaDocumentVerificationDetailView,
    AdminFincaDocumentVerificationListView,
)

app_name = 'verification'

urlpatterns = [
   path('',AdminFincaDocumentVerificationListView.as_view(),name='list',),
   path('create/',AdminFincaDocumentVerificationCreateView.as_view(),name='create',),
   path('<int:pk>/',AdminFincaDocumentVerificationDetailView.as_view(),name='detail',),
]