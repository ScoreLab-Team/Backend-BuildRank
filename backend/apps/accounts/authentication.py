from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

from apps.accounts.models import AccountStatus


class AccountStatusJWTAuthentication(JWTAuthentication):
    """
    Extends JWTAuthentication to reject requests from blocked or suspended users.
    Checked on every authenticated request so that status changes take effect
    immediately without waiting for token expiry.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        self._enforce_account_status(user)
        return user

    def _enforce_account_status(self, user):
        profile = getattr(user, "profile", None)
        if profile is None:
            return

        if profile.account_status == AccountStatus.BLOCKED:
            raise AuthenticationFailed(
                detail="Aquest compte ha estat bloquejat. Contacteu amb l'administrador.",
                code="account_blocked",
            )

        if profile.account_status == AccountStatus.SUSPENDED:
            until = profile.suspended_until
            # None → indefinite suspension; future date → still active suspension
            if until is None or until > timezone.now():
                raise AuthenticationFailed(
                    detail="Aquest compte està suspès temporalment.",
                    code="account_suspended",
                )
            # Suspension period has expired — auto-lift so the DB reflects reality.
            profile.account_status = AccountStatus.ACTIVE
            profile.suspension_reason = ""
            profile.suspended_until = None
            profile.save(update_fields=["account_status", "suspension_reason", "suspended_until"])
