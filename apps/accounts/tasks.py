"""Periodic privacy lifecycle tasks for accounts."""

from celery import shared_task

from .privacy import process_inactive_accounts


@shared_task(name="apps.accounts.tasks.process_inactive_accounts")
def process_inactive_accounts_task() -> dict[str, int]:
    return process_inactive_accounts()
