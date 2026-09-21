"""Алиас «S.E.B.» бренда СЕБ (BURY-MEDIA-PILOT-01 ADJUST).

На ВИ буры СЕБ продаются как «S.E.B.» (карточка «Бур по бетону SDS+ 16x800 мм
S.E.B. 403BL-P16800» — точный наш артикул и размер), а в словаре у СЕБ был только
«себ». Матчер коллектора видел ``article_exact+brand_conflict`` / ``brand_unknown`` и
не брал фото. Добавлена только точечная форма с точками; голое «seb» — нет.

БД не требуется.
"""

from __future__ import annotations

from apps.catalog.brand_identity import decide_brand
from apps.catalog.brand_vocabulary import load_brand_vocabulary

VOCAB = load_brand_vocabulary()


def test_seb_dotted_maps_to_canonical():
    assert VOCAB.canonical_by_alias.get("s.e.b.") == "СЕБ"


def test_vi_card_title_resolves_to_seb():
    decision = decide_brand("Бур по бетону SDS-max 25x800 мм S.E.B. 403BL-M25800")
    assert "СЕБ" in decision.manufacturers


def test_bare_seb_not_added():
    # «SEB» — ещё и Groupe SEB (бытовая техника): без точек форма не подтверждена данными.
    assert "seb" not in VOCAB.canonical_by_alias


def test_existing_cyrillic_alias_unaffected():
    assert VOCAB.canonical_by_alias.get("себ") == "СЕБ"
    assert "СЕБ" in decide_brand("Бур 6х160 мм SDS PLUS СЕБ").manufacturers
