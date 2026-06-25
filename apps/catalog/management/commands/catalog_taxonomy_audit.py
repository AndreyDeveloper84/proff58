"""Аудит публичной таксономии каталога (Фаза 1 редизайна, read-only).

Считает объёмы товаров по реальному дампу 1С (``data/catalog_fixed.json``),
сверяет три оси (категория / tool_type / характеристика) и пишет отчёты в
``docs/reports/``. БД не требуется, файлы ``data/`` только читаются — команда
безопасна и идемпотентна (перезаписывает только свои отчёты).

    ./manage.py catalog_taxonomy_audit
    ./manage.py catalog_taxonomy_audit --out docs/reports --echo

См. ``apps/catalog/taxonomy_audit.py`` (чистая логика) и
``docs/plans/catalog-taxonomy-redesign.md`` (план редизайна).
"""

from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.ingest import load_json
from apps.catalog.taxonomy_audit import AuditResult, analyze

_AUDIT = "catalog-taxonomy-audit.md"
_COVERAGE = "catalog-taxonomy-coverage.md"
_MAPPING = "catalog-taxonomy-mapping.md"


class Command(BaseCommand):
    help = "Аудит публичной таксономии каталога: 3 отчёта в docs/reports (read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default=None,
            help="Каталог для отчётов (по умолчанию <BASE_DIR>/docs/reports).",
        )
        parser.add_argument(
            "--echo",
            action="store_true",
            help="Печатать audit-отчёт в stdout (файлы всё равно пишутся).",
        )

    def handle(self, *args, **options):
        # Отсутствующий/битый data-файл — понятная CommandError, а не голый трейсбек
        # (json.JSONDecodeError — подкласс ValueError).
        try:
            mapping = load_json("group_mapping.json")
            tree = load_json("catalog_fixed.json")
            tt_rules = load_json("tool_type_rules.json")
            attr_rules = load_json("attribute_rules.json")
        except (FileNotFoundError, ValueError) as exc:
            raise CommandError(f"Не удалось прочитать data-файлы каталога: {exc}") from exc

        result = analyze(mapping, tree, tt_rules, attr_rules)

        out_dir = (
            Path(options["out"]) if options["out"] else Path(settings.BASE_DIR) / "docs" / "reports"
        )
        out_dir.mkdir(parents=True, exist_ok=True)

        audit_md = render_audit(result)
        (out_dir / _AUDIT).write_text(audit_md, encoding="utf-8")
        (out_dir / _COVERAGE).write_text(render_coverage(result), encoding="utf-8")
        (out_dir / _MAPPING).write_text(render_mapping(result), encoding="utf-8")

        if options["echo"]:
            self.stdout.write(audit_md)

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: {result.total_products} товаров; on_site={result.mapped_onsite}, "
                f"скрыто={result.offsite}, без маппинга={result.unmapped}; "
                f"находок={len(result.findings)}. Отчёты → {out_dir}"
            )
        )


# --- Рендер отчётов (markdown) ----------------------------------------------

_HEADER = (
    "<!-- Сгенерировано `manage.py catalog_taxonomy_audit` (read-only). "
    "Правки вносить в исходные данные/команду, не в этот файл. -->\n\n"
)


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):.1f}%" if whole else "—"


def render_audit(r: AuditResult) -> str:
    lines = [_HEADER, "# Аудит таксономии каталога\n"]
    lines.append(
        "**Источник:** `data/catalog_fixed.json` (реальный дамп 1С), "
        "`data/group_mapping.json`, `data/tool_type_rules.json`, "
        "`data/attribute_rules.json`.\n"
    )
    lines.append("## Сводка\n")
    lines.append(f"- Всего товаров: **{r.total_products}**")
    lines.append(
        f"- Замаплено в публичное дерево (on_site): **{r.mapped_onsite}** "
        f"({_pct(r.mapped_onsite, r.total_products)})"
    )
    lines.append(
        f"- Намеренно скрыто (off_site, грязь 1С): **{r.offsite}** "
        f"({_pct(r.offsite, r.total_products)})"
    )
    lines.append(f"- Без маппинга (в «Неразобранные»): **{r.unmapped}**\n")

    lines.append("## Разделы верхнего уровня\n")
    lines.append("| Раздел | Товаров | Подкатегорий |")
    lines.append("|---|---:|---:|")
    for name, cnt, nchild in r.roots:
        lines.append(f"| {name} | {cnt} | {nchild} |")
    lines.append("")

    lines.append("### Глубина категорий (распределение листьев site_path)\n")
    for d in sorted(r.depth_hist):
        lines.append(f"- depth={d}: {r.depth_hist[d]}")
    lines.append("")

    lines.append("## Находки\n")
    sev_order = {"high": 0, "medium": 1, "low": 2}
    for f in sorted(r.findings, key=lambda x: sev_order.get(x.severity, 9)):
        lines.append(f"### [{f.code}] {f.title}  _(severity: {f.severity})_\n")
        if f.rows:
            lines.append("| Узел | Товаров |")
            lines.append("|---|---:|")
            for node, cnt in f.rows:
                lines.append(f"| {node} | {cnt if cnt else ''} |")
            lines.append("")
        lines.append(f"**Рекомендация:** {f.recommendation}\n")

    lines.append("## Off_site группы (скрыты под скрытым корнем, ADR-0002)\n")
    lines.append("| Группа 1С | Товаров |")
    lines.append("|---|---:|")
    for name, cnt in r.offsite_rows:
        lines.append(f"| {name} | {cnt} |")
    lines.append("")
    return "\n".join(lines)


def render_coverage(r: AuditResult) -> str:
    lines = [_HEADER, "# Покрытие осей таксономии (tool_type / характеристики)\n"]
    lines.append(
        "> Объёмы товаров — из реального дампа 1С. **Живое** покрытие `tool_type` и "
        "атрибутов по товарам (доля заполненных EAV) считается на staging с БД "
        "(`enrich_tool_type` / `enrich_attributes` + `attribute_coverage`); здесь — "
        "**спроектированное** покрытие из правил `data/*.json`.\n"
    )

    axes = r.designed_axes
    lines.append("## Спроектированные tool_type по разделам\n")
    lines.append("| Раздел | Товаров | tool_type'ов в правилах |")
    lines.append("|---|---:|---:|")
    root_count = {name: cnt for name, cnt, _ in r.roots}
    for cat, n in sorted(axes["tool_types_per_category"].items(), key=lambda kv: -(kv[1] or 0)):
        lines.append(f"| {cat} | {root_count.get(cat, '—')} | {n} |")
    lines.append("")

    lines.append("## Спроектированные характеристики по tool_type\n")
    lines.append("| tool_type | Раздел | Атрибутов | filter | seo |")
    lines.append("|---|---|---:|---:|---:|")
    for tt, info in sorted(
        axes["attributes_per_tool_type"].items(), key=lambda kv: -kv[1]["total"]
    ):
        lines.append(
            f"| {tt} | {info['category']} | {info['total']} | {info['filter']} | {info['seo']} |"
        )
    lines.append("")
    lines.append(
        "**Проблемная зона:** разделы с большим числом товаров, но без описанных "
        "tool_type/атрибутов (нет строки в таблицах выше) — кандидаты на "
        "характеризацию (скилл `characterize-subgroup`).\n"
    )
    return "\n".join(lines)


def render_mapping(r: AuditResult) -> str:
    lines = [_HEADER, "# Маппинг и целевая стратегия по категориям\n"]
    lines.append(
        "Колонка _Рекомендация_ — производная от находок аудита; финальное решение "
        "принимается владельцем в `docs/plans/catalog-taxonomy-redesign.md`.\n"
    )
    # карта узел → коды находок
    note: dict[str, list[str]] = {}
    for f in r.findings:
        for node, _ in f.rows:
            note.setdefault(node, []).append(f.code)

    lines.append("## Текущие публичные категории (по объёму)\n")
    lines.append("| Публичная категория (site_path) | Товаров | Находки |")
    lines.append("|---|---:|---|")
    for s in r.categories:
        path = " / ".join(s.path)
        codes = ", ".join(note.get(path, []))
        lines.append(f"| {path} | {s.count} | {codes} |")
    lines.append("")
    lines.append(
        "## Принцип маппинга 1С → публичная категория\n\n"
        "- Ключ связи — `external_id` **родительской** группы 1С (стабилен; имя не "
        "уникально). Маппинг ведётся в `data/group_mapping.json`.\n"
        "- Бренд из имени группы → `Product.brand`, не в категорию (находки F4).\n"
        "- Характеристика из имени группы → EAV-атрибут, не в категорию.\n"
        "- Грязь/служебные группы 1С → `on_site:false` (скрытый корень, ADR-0002).\n"
        "- Внутренние под-типы (Буры/Свёрла/Метчики…) берутся из 1С-подгрупп либо из "
        "`tool_type` по названию — публичная иерархия не обязана повторять 1С.\n"
    )
    return "\n".join(lines)
