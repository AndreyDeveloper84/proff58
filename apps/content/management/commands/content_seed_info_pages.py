"""Завести инфо-страницы из макетов в админку (DRF-1013).

Вёрстка блоков живёт в коде, содержимое — в админке. Но пустая админка не
наполнится сама: страницу с готовой структурой кто-то должен положить. Команда
переносит тексты из ``data/info_pages/*.md`` в ``SEOPage`` — дальше их правит
человек, а не разработчик.

    ./manage.py content_seed_info_pages              # dry-run: что будет создано
    ./manage.py content_seed_info_pages --commit     # завести (черновиками)
    ./manage.py content_seed_info_pages --commit --publish   # сразу опубликовать

Страницы заводятся **черновиками**: в текстах есть вопросы без ответов и условия
доставки, которые должен подтвердить владелец. Публикация — его решение, а не
побочный эффект прогона.

Уже существующую страницу команда не трогает, если её правили: перезаписать —
значит стереть работу редактора. Такие страницы перечисляются в отчёте, и только
``--force`` заставит обновить их из файла.

Формат файла: строки ``ключ: значение`` (title, meta_title, meta_description),
пустая строка, дальше разметка страницы (см. ``apps/content/page_markup.py``).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.content.models import PublishStatus, SEOPage

SEED_DIR = "info_pages"
HEADER_KEYS = ("title", "meta_title", "meta_description")


def parse_seed(text: str) -> dict:
    """Шапка «ключ: значение» до первой пустой строки, дальше — тело страницы."""
    header: dict[str, str] = {}
    lines = text.splitlines()
    index = 0
    for index, line in enumerate(lines):  # noqa: B007 — индекс нужен после цикла
        if not line.strip():
            break
        key, sep, value = line.partition(":")
        key = key.strip().lower()
        if not sep or key not in HEADER_KEYS:
            break
        header[key] = value.strip()
    if "title" not in header:
        raise CommandError("В файле нет строки «title: …» — без заголовка страница не заводится.")
    header["body"] = "\n".join(lines[index:]).strip() + "\n"
    return header


class Command(BaseCommand):
    help = "Завести инфо-страницы из data/info_pages/*.md в админку."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--publish", action="store_true", help="Публиковать созданные сразу.")
        parser.add_argument("--force", action="store_true", help="Перезаписать правленые страницы.")
        parser.add_argument("--dir", metavar="PATH", help="Своя папка с файлами страниц.")

    def handle(self, *args, **options):
        directory = Path(options["dir"] or Path(settings.BASE_DIR) / "data" / SEED_DIR)
        files = sorted(directory.glob("*.md"))
        if not files:
            raise CommandError(f"В {directory} нет ни одного файла страницы.")

        create, update, skip = [], [], []
        for path in files:
            data = parse_seed(path.read_text(encoding="utf-8"))
            page = SEOPage.objects.filter(slug=path.stem).first()
            if page is None:
                create.append((path.stem, data))
            elif page.body.strip() == data["body"].strip():
                skip.append((path.stem, "уже совпадает"))
            elif options["force"]:
                update.append((page, data))
            else:
                skip.append((path.stem, "правилась в админке — не трогаю (--force перезапишет)"))

        self._report(create, update, skip, publish=options["publish"])
        if not (create or update):
            return
        if not options["commit"]:
            self.stdout.write(self.style.WARNING("\nDRY-RUN: ничего не записано. Применить — --commit."))
            return

        status = PublishStatus.PUBLISHED if options["publish"] else PublishStatus.DRAFT
        with transaction.atomic():
            for slug, data in create:
                SEOPage.objects.create(
                    slug=slug,
                    title=data["title"],
                    meta_title=data.get("meta_title", ""),
                    meta_description=data.get("meta_description", ""),
                    body=data["body"],
                    status=status,
                )
            for page, data in update:
                page.title = data["title"]
                page.meta_title = data.get("meta_title", "")
                page.meta_description = data.get("meta_description", "")
                page.body = data["body"]
                page.save()
        self.stdout.write(
            self.style.SUCCESS(f"\nCOMMIT: создано {len(create)}, обновлено {len(update)}.")
        )

    def _report(self, create, update, skip, *, publish: bool):
        w = self.stdout.write
        w(self.style.MIGRATE_HEADING("\n=== Инфо-страницы из макетов ==="))
        state = "опубликованными" if publish else "черновиками"
        w(f"\nК созданию ({state}): {len(create)}")
        for slug, data in create:
            w(f"  /{slug} — {data['title']}")
        if update:
            w(self.style.WARNING(f"\nК перезаписи (--force): {len(update)}"))
            for page, _data in update:
                w(f"  /{page.slug} — {page.title}")
        if skip:
            w(f"\nПропущено: {len(skip)}")
            for slug, reason in skip:
                w(f"  /{slug} — {reason}")
