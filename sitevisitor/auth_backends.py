from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model


class ModerationBlockBackend(ModelBackend):
    """
    Authentication backend that denies login for users permanently blocked by admin.
    Delegates credential verification to ModelBackend, then checks moderation profile.
    """

    def authenticate(self, request, **kwargs):
        user = super().authenticate(request, **kwargs)
        if user is None:
            return None

        try:
            from whatsappapi.models import UserModerationProfile
            mp, _ = UserModerationProfile.objects.get_or_create(user=user)
            # Allow staff/superuser even if flagged (administrative access)
            if mp and mp.permanently_blocked and not (user.is_staff or user.is_superuser):
                return None
        except Exception:
            # Fail-open on errors to avoid locking out legitimate users unexpectedly
            pass

        return user