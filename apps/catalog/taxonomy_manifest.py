"""Canonical tool_type taxonomy manifest (Wave 7.1 / Stage H1).

Единый versioned источник operational taxonomy для ``Attribute(slug="tool_type")``.
Отделён от legacy extraction rules (``data/tool_type_rules.json``): manifest
материализует options (slug/value/sort_order); extraction semantics здесь не
определяется и не меняется.

Runtime-контракт — только ``{slug, value}``; ``origin_*`` / ``review_*`` /
``legacy_aliases`` — audit-only metadata: в БД не загружаются, reslug/remapping
не вызывают.

Hashes (раздельные; НЕ смешиваются с legacy ``queue_contract._taxonomy_hash``,
который order-sensitive и зависит от DB collation):

- ``taxonomy_identity_hash`` — runtime identity: sha256 канонического
  (code-point sorted) списка ``{slug, value}``. sort_order/PK/display metadata
  не входят; environment-independent.
- ``manifest_semantic_hash`` — audit: sha256 семантического содержимого
  (versions + полные записи options, включая sort_order/origin/review/aliases).
- ``artifact_sha256`` — байты файла; в файле не хранится, вычисляется
  инструментами/CI (pinning для release manifest).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from jsonschema import Draft7Validator

from .tool_type import normalize

MANIFEST_PATH = (
    Path(settings.BASE_DIR) / "data" / "catalog_processing_rules" / "tool_type_taxonomy.v1.json"
)
SCHEMA_PATH = (
    Path(settings.BASE_DIR) / "apps" / "catalog" / "schemas" / "tool_type_taxonomy_v1.json"
)

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ORIGIN_KINDS = frozenset({"seed", "manual_backport", "legacy_unknown"})
REVIEW_STATUSES = frozenset({"approved", "pending_business_review"})


def _canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def taxonomy_identity_hash(options: list[dict]) -> str:
    """sha256 канонического списка ``{slug, value}`` (code-point sort by slug).

    Порядок задаётся явно внутри recipe — не зависит от DB collation и от
    порядка options во входном списке. sort_order/PK/display metadata не
    участвуют: изменение только UI-порядка identity hash не меняет.
    """
    canon = sorted(
        ({"slug": o["slug"], "value": o["value"]} for o in options),
        key=lambda o: o["slug"],
    )
    return hashlib.sha256(_canonical_json(canon).encode("utf-8")).hexdigest()


def manifest_semantic_hash(doc: dict) -> str:
    """sha256 семантического содержимого manifest (audit-контракт).

    Входит: schema_version, manifest_version, attribute_slug,
    semantic_duplicate_allowlist и полные записи options (включая
    sort_order/origin/review/aliases). Не входит: provenance,
    future_evolution и сами hash-поля.
    """
    payload = {
        "schema_version": doc["schema_version"],
        "manifest_version": doc["manifest_version"],
        "attribute_slug": doc["attribute_slug"],
        "semantic_duplicate_allowlist": doc.get("semantic_duplicate_allowlist", []),
        "options": doc["options"],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def artifact_sha256(path: Path) -> str:
    """sha256 сырых байтов файла (pinning; в файле не хранится)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True)
class ManifestOption:
    slug: str
    value: str
    sort_order: int = 0
    origin_kind: str = "seed"
    origin_ref: str | None = None
    review_status: str = "approved"
    review_reason: str = ""
    review_ref: str | None = None
    legacy_aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaxonomyManifest:
    schema_version: int
    manifest_version: int
    attribute_slug: str
    options: tuple[ManifestOption, ...]
    identity_hash: str
    semantic_hash: str
    path: Path

    @property
    def slugs(self) -> set[str]:
        return {o.slug for o in self.options}


def validate_manifest_doc(doc: dict) -> list[str]:
    """Fail-closed валидация содержимого manifest (поверх JSON Schema).

    Возвращает список нарушений (пустой = валиден). Покрывает: versions,
    пустые/невалидные slug и value, duplicate slug, duplicate semantic value
    вне explicit allow-list, enum origin/review, alias-инварианты
    (не собственный slug, не active slug другой option, без дублей) и
    пересчёт обоих hashes.
    """
    violations: list[str] = []
    for field_name in ("schema_version", "manifest_version"):
        v = doc.get(field_name)
        if not isinstance(v, int) or isinstance(v, bool) or v < 1:
            violations.append(f"{field_name} должен быть int >= 1: {v!r}")
    options = doc.get("options")
    if not isinstance(options, list) or not options:
        violations.append("options должен быть непустым списком")
        return violations

    seen_slugs: set[str] = set()
    by_value: dict[str, list[str]] = {}
    all_aliases: list[str] = []
    for o in options:
        slug = o.get("slug", "")
        value = o.get("value", "")
        label = slug or "<no-slug>"
        if not isinstance(slug, str) or not slug.strip():
            violations.append(f"пустой slug в option: {o!r}")
        elif not SLUG_RE.match(slug):
            violations.append(f"невалидный slug: {slug!r}")
        if not isinstance(value, str) or not value.strip():
            violations.append(f"{label}: пустой value")
        if slug in seen_slugs:
            violations.append(f"duplicate slug: {slug}")
        seen_slugs.add(slug)
        if isinstance(value, str):
            by_value.setdefault(value, []).append(slug)
        if o.get("origin_kind", "seed") not in ORIGIN_KINDS:
            violations.append(f"{label}: невалидный origin_kind {o.get('origin_kind')!r}")
        if o.get("review_status", "approved") not in REVIEW_STATUSES:
            violations.append(f"{label}: невалидный review_status {o.get('review_status')!r}")
        aliases = o.get("legacy_aliases", [])
        if not isinstance(aliases, list):
            violations.append(f"{label}: legacy_aliases не список")
            continue
        if slug in aliases:
            violations.append(f"{label}: alias совпадает с собственным slug")
        if len(aliases) != len(set(aliases)):
            violations.append(f"{label}: duplicate alias")
        all_aliases.extend(aliases)

    allow = {frozenset(pair) for pair in doc.get("semantic_duplicate_allowlist", [])}
    for value, slugs in by_value.items():
        if len(slugs) > 1 and frozenset(slugs) not in allow:
            violations.append(
                f"duplicate semantic value вне allow-list: {value!r} -> {sorted(slugs)}"
            )
    for alias in all_aliases:
        if alias in seen_slugs:
            violations.append(f"alias {alias!r} совпадает с active slug другой option")

    if "taxonomy_identity_hash" in doc and doc["taxonomy_identity_hash"] != taxonomy_identity_hash(
        options
    ):
        violations.append("taxonomy_identity_hash не совпадает с пересчитанным")
    if "manifest_semantic_hash" in doc and doc["manifest_semantic_hash"] != manifest_semantic_hash(
        doc
    ):
        violations.append("manifest_semantic_hash не совпадает с пересчитанным")
    return violations


def _load_schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_manifest(path: Path | None = None) -> TaxonomyManifest:
    """Загрузка manifest с JSON Schema + content валидацией. Fail-closed."""
    path = Path(path) if path else MANIFEST_PATH
    with path.open("r", encoding="utf-8") as f:
        doc = json.load(f)
    validator = Draft7Validator(_load_schema())
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.path))
    if errors:
        rendered = "; ".join(
            f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors
        )
        raise ValueError(f"taxonomy manifest не прошёл JSON Schema: {rendered}")
    violations = validate_manifest_doc(doc)
    if violations:
        raise ValueError("taxonomy manifest невалиден: " + "; ".join(violations))
    return TaxonomyManifest(
        schema_version=doc["schema_version"],
        manifest_version=doc["manifest_version"],
        attribute_slug=doc["attribute_slug"],
        options=tuple(
            ManifestOption(
                slug=o["slug"],
                value=o["value"],
                sort_order=o.get("sort_order", 0),
                origin_kind=o.get("origin_kind", "seed"),
                origin_ref=o.get("origin_ref"),
                review_status=o.get("review_status", "approved"),
                review_reason=o.get("review_reason", ""),
                review_ref=o.get("review_ref"),
                legacy_aliases=tuple(o.get("legacy_aliases", [])),
            )
            for o in doc["options"]
        ),
        identity_hash=doc["taxonomy_identity_hash"],
        semantic_hash=doc["manifest_semantic_hash"],
        path=path,
    )


class ManifestOptions:
    """Lookup-индексы manifest для runtime guard'ов.

    Используется только runtime-контракт (slug/value); audit metadata
    (origin/review/aliases) в индексы не попадает и на поведение не влияет.
    Value-индекс строится через тот же ``tool_type.normalize``, что и
    extraction-контур, — согласованность сопоставления.
    """

    def __init__(self, manifest: TaxonomyManifest):
        self._by_slug = {o.slug: o for o in manifest.options}
        self._by_value: dict[str, ManifestOption] = {}
        for o in manifest.options:
            self._by_value.setdefault(normalize(o.value), o)

    def by_slug(self, slug: str) -> ManifestOption | None:
        return self._by_slug.get(slug)

    def by_normalized_value(self, value: str) -> ManifestOption | None:
        return self._by_value.get(normalize(value))

    @property
    def slugs(self) -> set[str]:
        return set(self._by_slug)


def load_options_index(path: Path | None = None) -> ManifestOptions:
    """ManifestOptions из canonical manifest (для runtime guard'ов)."""
    return ManifestOptions(load_manifest(path))
