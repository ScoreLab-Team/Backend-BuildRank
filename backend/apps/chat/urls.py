from django.urls import path

from .views import (
    ChatChannelsProvisionView,
    ChatChannelsView,
    ChatTokenView,
    TwinBuildingAdminsView,
    TwinBuildingChannelView,
)

urlpatterns = [
    path("token/", ChatTokenView.as_view(), name="chat-token"),
    path("channels/", ChatChannelsView.as_view(), name="chat-channels"),
    path("channels/provision/", ChatChannelsProvisionView.as_view(), name="chat-channels-provision"),

    path(
        "twin-buildings/<int:edifici_id>/admins/",
        TwinBuildingAdminsView.as_view(),
        name="chat-twin-building-admins",
    ),
    path(
        "twin-buildings/<int:edifici_id>/channels/",
        TwinBuildingChannelView.as_view(),
        name="chat-twin-building-channel",
    ),
]