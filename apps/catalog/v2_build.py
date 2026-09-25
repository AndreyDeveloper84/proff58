"""Хелперы построения v2-дерева сайта (общие для build_skeleton/build_section).

Главное: НЕ переиспользовать легаси-категорию (зеркало группы 1С) как v2-корень.
Признак легаси — наличие ``external_id_1c`` на узле или в его поддереве. v2-узлы
помечаются ``is_site_v2=True`` (по нему «Категории (сайт)» отличает витринное дерево).
"""

from __future__ import annotations

from apps.catalog.models import Category


def _is_legacy(node: Category) -> bool:
    """Узел — легаси-зеркало 1С (есть код 1С на нём или в поддереве)."""
    if node.external_id_1c:
        return True
    return node.get_descendants().filter(external_id_1c__isnull=False).exists()


def resolve_v2_root(section_slug: str, name: str, *, visible: bool, created_ids=None):
    """Найти/создать v2-корень раздела по ``section_slug``.

    Переиспользует существующий узел ТОЛЬКО если он уже v2 или «чистый» (без кодов 1С).
    Если slug занят легаси — легаси уступает slug (переименовывается), v2 создаётся
    заново с этим slug и ``is_site_v2=True``. Возвращает (root, created_bool).
    """
    existing = Category.objects.filter(slug=section_slug).first()
    if existing is not None:
        if existing.is_site_v2 or not _is_legacy(existing):
            if not existing.is_site_v2:
                existing.is_site_v2 = True
                existing.save(update_fields=["is_site_v2"])
            return existing, False
        # slug занят легаси (есть коды 1С) — освобождаем slug под v2.
        existing.slug = f"legacy-{section_slug}-{existing.pk}"
        existing.save(update_fields=["slug"])

    root = Category.add_root(
        name=name, slug=section_slug, is_active=visible, on_site=visible, is_site_v2=True
    )
    if created_ids is not None:
        created_ids.append(root.pk)
    return root, True
