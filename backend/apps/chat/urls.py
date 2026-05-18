from django.urls import path

from .views import (
    BanFromChannelView,
    ChatChannelsProvisionView,
    ChatChannelsView,
    ChatTokenView,
    DeleteMessageView,
    DismissFlagView,
    FlagMessageView,
    GlobalBanView,
    GlobalUnbanView,
    HideMessageView,
    MuteUserView,
    RestoreMessageView,
    ShadowBanView,
    ShadowUnbanView,
    UnbanFromChannelView,
    UnmuteUserView,
    WarnUserView,
    TwinBuildingAdminsView,
    TwinBuildingChannelView,
)

urlpatterns = [
    path("token/", ChatTokenView.as_view(), name="chat-token"),
    path("channels/", ChatChannelsView.as_view(), name="chat-channels"),
    path("channels/provision/", ChatChannelsProvisionView.as_view(), name="chat-channels-provision"),

    # Message moderation
    path("moderation/messages/<str:message_id>/flag/", FlagMessageView.as_view(), name="chat-flag-message"),
    path("moderation/messages/<str:message_id>/hide/", HideMessageView.as_view(), name="chat-hide-message"),
    path("moderation/messages/<str:message_id>/", DeleteMessageView.as_view(), name="chat-delete-message"),
    path("moderation/messages/<str:message_id>/restore/", RestoreMessageView.as_view(), name="chat-restore-message"),
    path("moderation/messages/<str:message_id>/dismiss-flag/", DismissFlagView.as_view(), name="chat-dismiss-flag"),

    # User moderation
    path("moderation/users/<int:user_id>/warn/", WarnUserView.as_view(), name="chat-warn-user"),
    path("moderation/users/<int:user_id>/mute/", MuteUserView.as_view(), name="chat-mute-user"),
    path("moderation/users/<int:user_id>/unmute/", UnmuteUserView.as_view(), name="chat-unmute-user"),
    path("moderation/users/<int:user_id>/ban/", BanFromChannelView.as_view(), name="chat-ban-user"),
    path("moderation/users/<int:user_id>/unban/", UnbanFromChannelView.as_view(), name="chat-unban-user"),
    path("moderation/users/<int:user_id>/global-ban/", GlobalBanView.as_view(), name="chat-global-ban"),
    path("moderation/users/<int:user_id>/global-unban/", GlobalUnbanView.as_view(), name="chat-global-unban"),
    path("moderation/users/<int:user_id>/shadow-ban/", ShadowBanView.as_view(), name="chat-shadow-ban"),
    path("moderation/users/<int:user_id>/shadow-unban/", ShadowUnbanView.as_view(), name="chat-shadow-unban"),

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
