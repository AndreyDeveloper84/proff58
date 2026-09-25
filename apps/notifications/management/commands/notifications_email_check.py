"""Контрольное письмо через настроенный транспорт (DRF-2296).

    manage.py notifications_email_check --to адрес

Адрес указывается явно — команда не берёт получателей из настроек и ничего не
пишет в outbox: это проверка транспорта, а не уведомление.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.notifications.channels import ChannelError
from apps.notifications.channels.email import is_configured, send_email


class Command(BaseCommand):
    help = "Отправить контрольное письмо на указанный адрес через настроенный SMTP."

    def add_arguments(self, parser):
        parser.add_argument("--to", required=True, help="Адрес получателя контрольного письма")

    def handle(self, *args, **options):
        to = options["to"].strip()
        host = getattr(settings, "EMAIL_HOST", "") or "—"
        self.stdout.write(
            f"backend={settings.EMAIL_BACKEND}\nhost={host}:{settings.EMAIL_PORT} "
            f"tls={settings.EMAIL_USE_TLS} ssl={settings.EMAIL_USE_SSL}\n"
            f"from={settings.DEFAULT_FROM_EMAIL}\nto={to}"
        )
        if not is_configured():
            raise CommandError("EMAIL_HOST не задан — транспорт не настроен.")
        stamp = timezone.localtime().strftime("%d.%m.%Y %H:%M:%S")
        try:
            send_email(
                "Проверка почты сайта «Профессионал»",
                f"Контрольное письмо от {stamp}. Если вы его читаете, транспорт работает.",
                [to],
            )
        except ChannelError as exc:
            raise CommandError(f"Отправка не удалась: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("Письмо отправлено."))
