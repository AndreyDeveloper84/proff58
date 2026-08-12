"""TT-15 · живые проверки витрины dev.proff58.ru.

Сверка API-выдачи и фасетов с числами, посчитанными напрямую в БД стенда
(eligible = is_active + published, фильтр по EAV — как ProductFilter.filter_tool_type).
"""
import json
import urllib.request

BASE = "https://dev.proff58.ru"

# Ожидания, посчитанные SQL по стенду после записи TT-15
API_COUNTS = {
    "bp-golovki-trimmernye": 72,
    "hoz-voronki": 5,
    "izm-multimetry": 73,
    "prochaya-osnastka": 386,
    "krep-gaiki": 39,
    "krep-bolty": 194,
    "obor-smazka": 61,
    "avtomaty-predohraniteli": 1,
}

C1_ACTIVE = [6743, 6744, 6745] + list(range(26238, 26242))  # сокращённо, полный список ниже
C1_ACTIVE = [6743, 6744, 6745, 26238, 26239, 26240, 26241, 26243, 26244, 26245, 26246,
             26247, 26248, 26249, 26250, 26251, 26252, 26253, 26255, 26256, 26257, 26258,
             26259, 26264, 26266, 26268, 26269, 26271, 26273, 26274, 26275, 26276, 26277,
             26278, 26282, 26284, 26289, 26290, 26291, 26297, 26299, 26300, 26301, 26302,
             26303, 26304, 26305, 26306, 26307, 26308, 26309, 26310, 26311, 26312, 26313,
             26314, 26315, 26316, 26317, 26318, 26319, 26320, 26321, 26322, 26323, 26324,
             26325, 26326, 26328, 26329, 26330, 26331]

PRESENT = {
    "bp-golovki-trimmernye": C1_ACTIVE,
    "hoz-voronki": [35608, 39284, 39286, 39290, 39291],
    "izm-multimetry": [18],
}
ABSENT = {
    "prochaya-osnastka": C1_ACTIVE,
    "krep-gaiki": [pid for pid in C1_ACTIVE],  # все активные C1 ушли из исходных типов
    "krep-bolty": [pid for pid in C1_ACTIVE],
    "obor-smazka": [39290],
}

FACETS = {
    # tool_type-панель сконфигурирована только в этих категориях (наследование
    # CategoryAttribute от предка); в osnastka-prochaya и категориях воронок панели
    # нет by design (привязок нет — конфиг, TT-15 его не трогал), а
    # hoztovary-sad-ogorod и avto-na-moderaciyu неактивны → 404 by design.
    "krepezh-gayki": {"bp-golovki-trimmernye": 5},
    "krepezh-bolty": {"bp-golovki-trimmernye": 3},
}

FAILS = []


def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check(name, ok, detail=""):
    print(f"{'OK  ' if ok else 'FAIL'} {name} {detail}")
    if not ok:
        FAILS.append(name)


def find_option_count(node, slug):
    """Рекурсивно найти счётчик опции slug в ответе фасетов."""
    if isinstance(node, dict):
        if node.get("slug") == slug and ("count" in node or "doc_count" in node):
            return node.get("count", node.get("doc_count"))
        for v in node.values():
            r = find_option_count(v, slug)
            if r is not None:
                return r
    elif isinstance(node, list):
        for v in node:
            r = find_option_count(v, slug)
            if r is not None:
                return r
    return None


print("=== 1. Счётчики API ?tool_type= против БД ===")
for slug, want in API_COUNTS.items():
    data = fetch(f"/api/catalog/products/?tool_type={slug}&limit=1")
    got = data.get("count")
    check(f"count {slug}", got == want, f"api={got} db={want}")

print("\n=== 2. Перенесённые присутствуют в целевых типах ===")
for slug, ids in PRESENT.items():
    data = fetch(f"/api/catalog/products/?tool_type={slug}&limit=2000")
    have = {p["id"] for p in data.get("results", [])}
    missing = sorted(set(ids) - have)
    check(f"present {slug}", not missing, f"missing={missing[:5]}" if missing else f"({len(ids)} pids)")

print("\n=== 3. Перенесённые отсутствуют в исходных типах ===")
for slug, ids in ABSENT.items():
    data = fetch(f"/api/catalog/products/?tool_type={slug}&limit=2000")
    have = {p["id"] for p in data.get("results", [])}
    offenders = sorted(set(ids) & have)
    check(f"absent {slug}", not offenders, f"offenders={offenders[:5]}" if offenders else "")

print("\n=== 4. Фасеты категорий против БД ===")
for cat, expects in FACETS.items():
    data = fetch(f"/api/catalog/categories/{cat}/facets/")
    for slug, want in expects.items():
        got = find_option_count(data, slug)
        check(f"facet {cat} :: {slug}", got == want, f"api={got} db={want}")

print(f"\n=== {'ALL OK' if not FAILS else f'FAILURES: {FAILS}'} ===")
