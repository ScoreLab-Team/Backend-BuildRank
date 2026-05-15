from django.urls import path

from .views import ChatChannelsProvisionView, ChatChannelsView, ChatTokenView

urlpatterns = [
    path("token/", ChatTokenView.as_view(), name="chat-token"),
    path("channels/", ChatChannelsView.as_view(), name="chat-channels"),
    path("channels/provision/", ChatChannelsProvisionView.as_view(), name="chat-channels-provision"),
]
