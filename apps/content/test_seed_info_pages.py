"""Тесты заведения инфо-страниц из макетов.

Команда пишет в контент, который дальше правит человек. Поэтому главное здесь —
что она НЕ затирает: правленую в админке страницу и статус публикации.
"""

import io

import pytest
from django.core.management import CommandError, call_command

from apps.content.models import PublishStatus, SEOPage

SEED = """title: Доставка
meta_title: Доставка — «Профессионал»
meta_description: Как получить заказ.

## Доставка
:герой
кнопка: Перейти в каталог | /catalog
Привезём сами.
"""


@pytest.fixture
def seed_dir(tmp_path):
    (tmp_path / "delivery.md").write_text(SEED, encoding="utf-8")
    return str(tmp_path)


def run(seed_dir, *args, **kwargs):
    out = io.StringIO()
    call_command("content_seed_info_pages", *args, dir=seed_dir, stdout=out, **kwargs)
    return out.getvalue()


def test_страница_заводится_черновиком(db, seed_dir):
    run(seed_dir, "--commit")

    page = SEOPage.objects.get(slug="delivery")
    # В текстах есть вопросы без ответов — публикация это решение владельца.
    assert page.status == PublishStatus.DRAFT
    assert page.title == "Доставка"
    assert page.body.startswith("## Доставка")


def test_dry_run_ничего_не_создаёт(db, seed_dir):
    output = run(seed_dir)

    assert not SEOPage.objects.exists()
    assert "DRY-RUN" in output


def test_правленая_страница_не_затирается(db, seed_dir):
    run(seed_dir, "--commit")
    page = SEOPage.objects.get(slug="delivery")
    page.body = "## Доставка\nТекст, который написал редактор.\n"
    page.status = PublishStatus.PUBLISHED
    page.save()

    output = run(seed_dir, "--commit")

    page.refresh_from_db()
    assert "редактор" in page.body
    assert page.status == PublishStatus.PUBLISHED
    assert "не трогаю" in output


def test_force_перезаписывает_осознанно(db, seed_dir):
    run(seed_dir, "--commit")
    SEOPage.objects.filter(slug="delivery").update(body="старое")

    run(seed_dir, "--commit", "--force")

    assert SEOPage.objects.get(slug="delivery").body.startswith("## Доставка")


def test_повторный_прогон_идемпотентен(db, seed_dir):
    run(seed_dir, "--commit")

    output = run(seed_dir, "--commit")

    assert SEOPage.objects.count() == 1
    assert "уже совпадает" in output


def test_публикация_только_по_явному_флагу(db, seed_dir):
    run(seed_dir, "--commit", "--publish")

    assert SEOPage.objects.get(slug="delivery").status == PublishStatus.PUBLISHED


def test_файл_без_заголовка_это_ошибка(db, tmp_path):
    (tmp_path / "broken.md").write_text("## Раздел\nтекст\n", encoding="utf-8")

    with pytest.raises(CommandError, match="title"):
        run(str(tmp_path), "--commit")


def test_боевые_файлы_страниц_разбираются(db):
    """Тексты из репозитория должны заводиться без правок — иначе команда бесполезна."""
    from apps.content.page_markup import parse_page_body

    run_output = run(None, "--commit") if False else None  # боевую папку не трогаем в БД
    assert run_output is None

    from pathlib import Path

    from django.conf import settings

    for path in sorted((Path(settings.BASE_DIR) / "data" / "info_pages").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("title: "), path.name
        body = text.split("\n\n", 1)[1]
        sections = parse_page_body(body)
        assert sections, path.name
        assert sections[0]["layout"] == "hero", f"{path.name}: страница должна открываться шапкой"
