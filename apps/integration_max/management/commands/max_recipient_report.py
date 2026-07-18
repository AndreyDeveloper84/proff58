"""Отчёт о рассинхроне legacy `User.max_chat_id` и `MaxAccount` (#514).

Только чтение — ничего не пишет и не мигрирует (полноценный backfill
невозможен: у legacy OTP-флоу нет `max_user_id`, обязательного для
`MaxAccount`). Помогает оценить трафик на задепрекейченный `handlers/auth.py`
и найти пользователей с расходящимся `chat_id` между legacy-полем и канонической
привязкой — их стоит разобрать вручную.

    python manage.py max_recipient_report
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.integration_max.models import MaxAccount

User = get_user_model()


class Command(BaseCommand):
    help = "Отчёт о рассинхроне legacy User.max_chat_id и MaxAccount (read-only, #514)."

    def handle(self, *args, **options):
        legacy_only = User.objects.filter(
            max_chat_id__isnull=False, max_account__isnull=True
        ).order_by("pk")

        conflicts = []
        accounts = MaxAccount.objects.filter(is_active=True, chat_id__isnull=False).select_related(
            "user"
        )
        for acct in accounts:
            legacy_chat_id = acct.user.max_chat_id
            if legacy_chat_id is not None and legacy_chat_id != acct.chat_id:
                conflicts.append((acct.user_id, legacy_chat_id, acct.chat_id))

        self.stdout.write(f"legacy-only (есть max_chat_id, нет MaxAccount): {legacy_only.count()}")
        for user in legacy_only:
            self.stdout.write(f"  user={user.pk}")

        self.stdout.write(f"конфликт chat_id (legacy != MaxAccount.chat_id): {len(conflicts)}")
        for user_id, legacy_chat_id, canonical_chat_id in conflicts:
            self.stdout.write(
                f"  user={user_id} legacy={legacy_chat_id} canonical={canonical_chat_id}"
            )
