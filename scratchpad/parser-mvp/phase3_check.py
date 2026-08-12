"""Phase 3: проверка карты scraped_attr_map.perforatory.json на выгрузке Phase 2.

Read-only: БД опрашивается только SELECT'ами через psql, выгрузка только читается.
Проверяет:
  [1] каждый атрибут/опция карты существует в БД и привязан к категории id=3;
  [2] каждое поле каждой карточки имеет решение в карте (unknown = 0 — иначе FAIL);
  [3] нормализацию всех сопоставленных значений (диапазоны, запятые, опции);
  [4] перекрёстную сверку power таблица vs summary_raw у resanta;
  [5] покрытие: handled (map+ignore+unmapped) и mapped доли по частоте;
  [6] детерминированную выборку для поштучной сверки (sort + stride).
"""
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
MAP_PATH = ROOT / "data/catalog_processing_rules/scraped_attr_map.perforatory.json"
OUT_DIR = HERE / "output"
SOURCES = ["resanta", "vihr", "interskol", "zubr"]

_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
_POWER_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*Вт")


def to_float(s: str) -> float:
    return float(s.replace(",", "."))


def norm_int(v: str) -> int:
    return int(to_float(_NUM_RE.search(v).group(0)))


def norm_decimal(v: str) -> float:
    return to_float(_NUM_RE.search(v).group(0))


def norm_range_upper(v: str) -> float:
    nums = _NUM_RE.findall(v)
    if not nums:
        raise ValueError(f"нет числа: {v!r}")
    return to_float(nums[-1]) if re.search(r"\d\s*-\s*\d", v) else to_float(nums[0])


def norm_voltage_first(v: str) -> float:
    return to_float(_NUM_RE.search(v).group(0))


def norm_summary_power(v: str) -> int:
    return int(to_float(_POWER_RE.search(v).group(1)))


def psql(sql: str) -> list[str]:
    res = subprocess.run(
        ["docker", "compose", "exec", "-T", "db", "psql", "-U", "proff", "-d", "proff58", "-Atc", sql],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr}")
    return [line for line in res.stdout.splitlines() if line.strip()]


def main() -> int:
    amap = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    out = []
    log = out.append
    fail = False

    # --- [1] существование атрибутов и опций в БД ---
    attrs: dict[str, dict] = {}  # slug -> info из карты
    option_refs: dict[str, set] = {}  # attr -> {option_slugs}
    for src, sdata in amap["sources"].items():
        for field, e in sdata["fields"].items():
            if e["action"] == "map":
                attrs.setdefault(e["attribute"], {"type": e["attribute_type"]})
                if e["attribute_type"] == "select":
                    option_refs.setdefault(e["attribute"], set()).update(e["values"].values())
        for e in sdata.get("fallbacks", []) + sdata.get("derived", []):
            attrs.setdefault(e["attribute"], {"type": e["attribute_type"]})
            if e["attribute_type"] == "select":
                option_refs.setdefault(e["attribute"], set()).add(e.get("value", ""))

    log("=== [1] Атрибуты карты в БД (SELECT) ===")
    slugs = sorted(attrs)
    rows = psql(
        "SELECT a.slug, a.attribute_type, a.unit, "
        "CASE WHEN ca.category_id IS NULL THEN 'НЕ ПРИВЯЗАН' ELSE 'cat=3 OK' END "
        "FROM catalog_attribute a "
        "LEFT JOIN catalog_categoryattribute ca ON ca.attribute_id=a.id AND ca.category_id=3 "
        f"WHERE a.slug IN ({','.join(repr(s) for s in slugs)}) ORDER BY a.slug"
    )
    db_attrs = {}
    for r in rows:
        slug, atype, unit, bind = r.split("|")
        db_attrs[slug] = (atype, unit, bind)
        log(f"  {slug}: type={atype} unit={unit or '-'} {bind}")
    for slug in slugs:
        if slug not in db_attrs:
            log(f"  FAIL: атрибут {slug} отсутствует в БД")
            fail = True
        elif db_attrs[slug][2] != "cat=3 OK":
            log(f"  FAIL: атрибут {slug} не привязан к категории id=3")
            fail = True

    log("=== [1b] Опции select-атрибутов в БД (SELECT) ===")
    for attr, opts in sorted(option_refs.items()):
        rows = psql(
            "SELECT o.slug FROM catalog_attributeoption o "
            "JOIN catalog_attribute a ON a.id=o.attribute_id "
            f"WHERE a.slug='{attr}' ORDER BY o.slug"
        )
        db_opts = set(rows)
        missing = opts - db_opts
        log(f"  {attr}: нужны {sorted(opts)}; в БД {sorted(db_opts)}; "
            f"{'OK' if not missing else 'FAIL нет: ' + str(sorted(missing))}")
        if missing:
            fail = True

    # --- [2..5] прогон карты на 32 карточках ---
    log("=== [2] Прогон на выгрузке Phase 2 ===")
    normalized: list[tuple] = []  # (attribute, source, sku, field, raw, value)
    dropped: list[tuple] = []
    stats = {s: Counter() for s in SOURCES}
    fieldfreq = {s: Counter() for s in SOURCES}
    crosscheck = []

    for src in SOURCES:
        data = json.loads((OUT_DIR / f"{src}.products.json").read_text(encoding="utf-8"))
        sdata = amap["sources"][src]
        for p in data["products"]:
            sku = p.get("manufacturer_sku") or p["name"]
            for field, raw in p["attributes"].items():
                fieldfreq[src][field] += 1
                e = sdata["fields"].get(field)
                if e is None:
                    stats[src]["unknown"] += 1
                    log(f"  UNKNOWN: {src} / {sku} / {field!r} = {raw!r}")
                    fail = True
                    continue
                action = e["action"]
                stats[src][action] += 1
                if action != "map":
                    continue
                try:
                    if e["attribute_type"] == "select":
                        key = raw.strip().lower()
                        if key not in e["values"]:
                            stats[src]["dropped"] += 1
                            dropped.append((src, sku, field, raw, "значение не в словаре опций"))
                            continue
                        val = e["values"][key]
                    elif e["normalize"] == "int":
                        val = norm_int(raw)
                    elif e["normalize"] == "decimal":
                        val = norm_decimal(raw)
                    elif e["normalize"] == "range_upper_decimal":
                        val = norm_range_upper(raw)
                    elif e["normalize"] == "voltage_first":
                        val = norm_voltage_first(raw)
                    else:
                        raise ValueError(f"неизвестный нормализатор {e['normalize']}")
                    normalized.append((e["attribute"], src, sku, field, raw, val))
                except Exception as ex:
                    stats[src]["dropped"] += 1
                    dropped.append((src, sku, field, raw, f"ошибка нормализации: {ex}"))
            # fallbacks
            for fb in sdata.get("fallbacks", []):
                if not any(f in p["attributes"] for f in fb["applies_when_missing"]):
                    raw = p.get("summary_raw")
                    if raw and fb["normalize"] == "summary_power_w" and _POWER_RE.search(raw):
                        val = norm_summary_power(raw)
                        stats[src]["fallback"] += 1
                        normalized.append((fb["attribute"], src, sku, "summary_raw", raw, val))
                    else:
                        stats[src]["dropped"] += 1
                        dropped.append((src, sku, "summary_raw", raw, "fallback: мощность не извлечена"))
            # derived
            for d in sdata.get("derived", []):
                if d["rule"] == "mains_if_voltage_field":
                    has_v = any("Напряжение" in f for f in p["attributes"])
                    if has_v:
                        stats[src]["derived"] += 1
                elif d["rule"] == "category_context_mains":
                    stats[src]["derived"] += 1
        # [4] перекрёстная сверка power у resanta: таблица vs summary
        if src == "resanta":
            for p in data["products"]:
                t = p["attributes"].get("Мощность, Вт")
                s = p.get("summary_raw") or ""
                m = _POWER_RE.search(s)
                if t and m:
                    ok = norm_int(t) == norm_summary_power(s)
                    crosscheck.append((p["manufacturer_sku"], t, m.group(1), ok))

    log("--- разбивка решений по источникам (вхождения полей) ---")
    tot = Counter()
    for src in SOURCES:
        c = stats[src]
        tot.update(c)
        log(f"  {src}: map={c['map']} fallback={c['fallback']} derived={c['derived']} "
            f"ignore={c['ignore']} unmapped={c['unmapped']} dropped={c['dropped']} unknown={c['unknown']}")
    log(f"  ИТОГО: {dict(tot)}")
    total_fields = sum(sum(c.values()) for c in fieldfreq.values())
    mapped_occ = tot["map"] + tot["fallback"]
    handled_occ = total_fields - tot["unknown"]
    log(f"--- покрытие по частоте ---")
    log(f"  всего вхождений полей: {total_fields}")
    log(f"  handled (map+ignore+unmapped): {handled_occ} = {handled_occ / total_fields * 100:.1f}%")
    log(f"  mapped к атрибутам (с fallback): {mapped_occ} = {mapped_occ / total_fields * 100:.1f}%")
    log(f"  derived (power_source): {tot['derived']} карточек")
    uniq = sum(len(c) for c in fieldfreq.values())
    log(f"  уникальных полей (по всем источникам): {uniq}, все имеют решение: "
        f"{'ДА' if tot['unknown'] == 0 else 'НЕТ'}")

    log("--- отброшенные при нормализации ---")
    for d in dropped:
        log(f"  {d[0]} / {d[1]} / {d[2]!r} = {str(d[3])[:60]!r} -> {d[4]}")
    if not dropped:
        log("  (нет)")

    log("--- [4] перекрёстная сверка power resanta (таблица vs summary_raw) ---")
    for sku, t, s, ok in crosscheck:
        log(f"  {sku}: таблица {t} Вт vs summary {s} Вт -> {'СОВПАЛО' if ok else 'РАСХОДИТСЯ'}")
        if not ok:
            fail = True

    # --- [6] детерминированная выборка ---
    log("=== [6] Выборка для поштучной сверки ===")
    pool = sorted(normalized, key=lambda r: (r[0], r[1], str(r[2]), r[3]))
    stride = max(1, len(pool) // 40)
    sample = pool[::stride]
    log(f"  критерий: все нормализованные значения (без derived), сортировка "
        f"(attribute, source, sku, field), stride={stride}; пул={len(pool)}, выборка={len(sample)}")
    (HERE / "phase3_sample.txt").write_text(
        "\n".join(
            f"{i + 1:3d}. [{a}] {s} / {sku} / {f} = {raw!r} -> {v}"
            for i, (a, s, sku, f, raw, v) in enumerate(sample)
        ),
        encoding="utf-8",
    )
    log(f"  выборка записана: phase3_sample.txt")

    # полный дамп нормализованных значений
    (HERE / "phase3_normalized_all.txt").write_text(
        "\n".join(f"[{a}] {s} / {sku} / {f} = {raw!r} -> {v}" for a, s, sku, f, raw, v in pool),
        encoding="utf-8",
    )
    log(f"  полный дамп ({len(pool)} значений): phase3_normalized_all.txt")

    text = "\n".join(out)
    (HERE / "phase3_check_out.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"\nRESULT: {'FAIL' if fail else 'OK'}")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
