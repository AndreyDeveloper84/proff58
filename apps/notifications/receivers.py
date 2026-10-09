"""Privacy cleanup subscribers for the notification domain."""

from apps.core import events


def on_user_deleted(sender, user_id=None, **kwargs):
    if user_id is None:
        return

    from .models import Notification, NotificationLog, UserNotificationPreference

    # User-facing history is owned by the deleted account.
    Notification.objects.filter(user_id=user_id).delete()
    UserNotificationPreference.objects.filter(user_id=user_id).delete()

    # Outbox is technical only; remove rows tied to the user instead of leaving
    # chat/email snapshots attached to an anonymized tombstone.
    NotificationLog.objects.filter(user_id=user_id).delete()


events.user_deleted.connect(on_user_deleted, dispatch_uid="notifications.user_deleted")
