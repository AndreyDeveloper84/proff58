"""Management-команда импорта номенклатуры 1С из файла.

Примеры:
    python manage.py import_1c data/nomenclature.json
    python manage.py import_1c data/price.csv --type prices
    python manage.py import_1c data/update.csv --update-only   # не создаёт новые товары
"""

from django.core.management.base import BaseCommand, CommandError

from apps.sync_1c import parsers, use_cases
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
            help="Только обновлять существующие товары (новые не создаются).",
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

        sync_log, result = use_cases.import_products(
            items,
            source_file=path,
            sync_type=options["type"],
            create_missing=not options["update_only"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Импорт завершён [{uid}]: создано {created}, обновлено {updated}, "
                "пропущено {skipped}, неразобранных {uncategorized}, ошибок {errors}.".format(
                    uid=sync_log.batch_uid, **result.as_dict()
                )
            )
        )
