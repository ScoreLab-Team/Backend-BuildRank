from django.urls import path

from .views import ChatChannelsView, ChatTokenView

urlpatterns = [
    path("token/", ChatTokenView.as_view(), name="chat-token"),
    path("channels/", ChatChannelsView.as_view(), name="chat-channels"),
]