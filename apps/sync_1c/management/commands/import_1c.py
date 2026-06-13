"""Management-команда импорта номенклатуры 1С из файла.

Примеры:
    python manage.py import_1c data/nomenclature.json
    python manage.py import_1c data/price.csv --type prices
"""

from django.core.management.base import BaseCommand, CommandError

from apps.sync_1c import importer, parsers
from apps.sync_1c.models import SyncLog


class Command(BaseCommand):
    help = "Импорт выгрузки 1С (JSON/CSV) в каталог через слой нормализации."

    def add_arguments(self, parser):
        parser.add_argument("path", help="Путь к файлу выгрузки (.json или .csv)")
        parser.add_argument(
            "--type",
            default=SyncLog.SyncType.FULL,
            choices=[c[0] for c in SyncLog.SyncType.choices],
            help="Тип прогона (по умолчанию full).",
        )
        parser.add_argument(
            "--update-only",
            action="store_true",
            help="Только обновлять существующие базовые поля (без жёсткой записи).",
        )

    def handle(self, *args, **options):
        path = options["path"]
        try:
            items = parsers.load_items(path)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        if not items:
            self.stdout.write(self.style.WARNING("Файл пуст — нечего импортировать."))
            return

        sync_log, result = importer.run_import(
            items,
            sync_type=options["type"],
            source_file=path,
            allow_basic_fields=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Импорт завершён [{uid}]: создано {created}, обновлено {updated}, "
                "неразобранных {uncategorized}, ошибок {errors}.".format(
                    uid=sync_log.batch_uid, **result.as_dict()
                )
            )
        )
