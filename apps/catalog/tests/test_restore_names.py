"""Подстановка названий, найденных в интернете (catalog_restore_names).

1С отдала 6 164 позиции с наименованием, обрезанным по 50 символов, и хвоста
нет ни у нас, ни в выгрузке — только во внешних источниках. Риск здесь в том,
что подставится неверное имя, поэтому проверок на отказ больше, чем на запись.
"""

import csv

import pytest
from django.core.management import call_command

from apps.catalog.models import Product

EVIDENCE = "https://stayer-rus.ru/remen-40562-6/"


def _csv(tmp_path, rows):
    path = tmp_path / "names.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "name", "evidence_url", "confidence"])
        writer.writerows(rows)
    return str(path)


@pytest.fixture
def truncated(db):
    return Product.objects.create(
        name='Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для креп',
        original_name='Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для креп',
        slug="styazhka-40562-6",
        article="40562-6",
    )


@pytest.mark.django_db
def test_applies_found_name(tmp_path, truncated):
    full = 'Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для крепления груза'
    call_command(
        "catalog_restore_names",
        f"--file={_csv(tmp_path, [[truncated.pk, full, EVIDENCE, 0.9]])}",
        "--commit",
        verbosity=0,
    )
    truncated.refresh_from_db()
    assert truncated.name == full
    # Источник зафиксирован — по нему видно, что имя пришло из веба, а не из 1С.
    assert truncated.content_field_sources["name"] == "web"
    assert truncated.content_source == "web"
    # Строка 1С осталась нетронутой: это по-прежнему точка отката.
    assert truncated.original_name == 'Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для креп'


@pytest.mark.django_db
def test_dry_run_writes_nothing(tmp_path, truncated):
    before = truncated.name
    call_command(
        "catalog_restore_names",
        f"--file={_csv(tmp_path, [[truncated.pk, 'Что угодно длиннее', EVIDENCE, 0.9]])}",
        verbosity=0,
    )
    truncated.refresh_from_db()
    assert truncated.name == before


@pytest.mark.django_db
def test_low_confidence_is_not_applied(tmp_path, truncated):
    """«Примерно похоже» покупателю показывать нельзя."""
    before = truncated.name
    call_command(
        "catalog_restore_names",
        f"--file={_csv(tmp_path, [[truncated.pk, 'Сомнительное имя', EVIDENCE, 0.4]])}",
        "--commit",
        verbosity=0,
    )
    truncated.refresh_from_db()
    assert truncated.name == before


@pytest.mark.django_db
def test_manual_name_is_not_overwritten(tmp_path, truncated):
    """Ручная правка менеджера приоритетнее найденного в интернете."""
    truncated.content_field_sources = {"name": "manual"}
    truncated.name = "Название, выверенное вручную"
    truncated.save()
    call_command(
        "catalog_restore_names",
        f"--file={_csv(tmp_path, [[truncated.pk, 'Имя из интернета', EVIDENCE, 0.95]])}",
        "--commit",
        verbosity=0,
    )
    truncated.refresh_from_db()
    assert truncated.name == "Название, выверенное вручную"


@pytest.mark.django_db
def test_evidence_url_is_required(tmp_path, truncated):
    """Без ссылки на источник предложение не принимается: проверить его нечем."""
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command(
            "catalog_restore_names",
            f"--file={_csv(tmp_path, [[truncated.pk, 'Имя без источника', '', 0.9]])}",
            "--commit",
            verbosity=0,
        )


@pytest.mark.django_db
def test_restore_truncated_does_not_undo_web_name(truncated):
    """`normalize_product_names --restore-truncated` не возвращает обрезанную строку 1С.

    Найденное в интернете имя длиннее исходника, поэтому под правило отката и не
    подпадает, но защита стоит явно: потерять восстановленное имя нельзя.
    """
    truncated.name = 'Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для крепления груза'
    truncated.content_field_sources = {"name": "web"}
    truncated.save()

    call_command("normalize_product_names", "--restore-truncated", verbosity=0)

    truncated.refresh_from_db()
    assert truncated.name.endswith("для крепления груза")


@pytest.mark.django_db
def test_inferred_source_needs_donor_not_url(tmp_path, truncated):
    """Достройка по позиции-донору из каталога — источник `inferred`.

    Ссылки у него нет, но донор обязателен: иначе непонятно, откуда взялся
    хвост. Приоритет у инференса ниже веба, поэтому находка из интернета его
    потом перекроет.
    """
    path = tmp_path / "inferred.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "name", "evidence_url", "confidence", "source"])
        writer.writerow(
            [
                truncated.pk,
                'Стяжка груза 6м, 2т STAYER "PROFESSIONAL" для крепления груза',
                "донор: product 12345",
                0.75,
                "inferred",
            ]
        )
    call_command("catalog_restore_names", f"--file={path}", "--commit", verbosity=0)
    truncated.refresh_from_db()
    assert truncated.name.endswith("для крепления груза")
    assert truncated.content_field_sources["name"] == "inferred"


@pytest.mark.django_db
def test_web_still_requires_https(tmp_path, truncated):
    from django.core.management.base import CommandError

    path = tmp_path / "bad.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["product_id", "name", "evidence_url", "confidence", "source"])
        writer.writerow([truncated.pk, "Имя", "донор: product 1", 0.9, "web"])
    with pytest.raises(CommandError):
        call_command("catalog_restore_names", f"--file={path}", "--commit", verbosity=0)
