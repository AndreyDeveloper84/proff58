# -*- coding: utf-8 -*-
"""CAT-07: классификатор prochaya-osnastka → кластеры (read-only, офлайн-анализ дампа).

Правила: (категория, regex по имени) → кластер с кандидатом типа из манифеста
(или None = типа нет, предложить). Порядок правил важен: первое сработавшее.
Остаток без кластера — «действительно прочее».
"""
import io
import json
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

raw = open("scratchpad/catalog/cat-07/prochaya_staging.json", encoding="utf-8").read()
rows = json.loads(raw[raw.index("["):])

# (кластер, cat_id или None, regex по имени (lower), кандидат типа из манифеста | "NEW:slug" | None)
RULES = [
    # --- класс 1: категория уже права ---
    ("semniki", 172, r"съемник|съёмник", "NEW:semniki"),
    ("telezhki", None, r"^тележк|^тачк", "obor-telezhki"),
    ("lebedki-tali", None, r"^таль\b|^лебедк|^лебёдк|^тельфер\b", "lebedki-tali"),
    ("yashchiki", 214, r"ящик|крышка|ремень", "yashchiki-sumki"),
    ("leska", None, r"^(яя)?леска\b", "bp-leska"),
    # --- класс 2: по имени ---
    ("stropy", None, r"\bстроп", "NEW:stropy-gruzovye"),
    ("smazki", None, r"\bсмазк", "str-smazki"),
    ("golovki-trimmernye", None, r"головка триммер|головка д/триммер|головка для триммер", "NEW:golovki-trimmernye"),
    ("katushki-trimmernye", None, r"катушка для триммер|катушка д/триммер", "NEW:katushki-trimmernye"),
    ("nozhi-trimmernye", None, r"нож для|нож д/|нож с зубцами|диск д/триммер|диск для триммер|диск д/кусторез|диск для кусторез|диск \(лезвие\)", "NEW:nozhi-diski-trimmernye"),
    ("dovodchiki", None, r"доводчик", "hoz-furnitura"),
    ("patrony-sverlilnye", None, r"\bпатроны?\b|патрон сверлильн|патрон ключевой|патрон быстрозажимн", "NEW:patrony-sverlilnye"),
    ("klyuchi-dlya-patronov", None, r"ключ (специальный )?(для|д/)\s?патрон", "aksessuary-dlya-klyuchey"),
    ("adaptery-vtulki", 103, r"втулка|адаптер|переходник|переходная", "zap-vtulki"),
    ("truborezy", None, r"труборез", "truborezy"),
    ("trubogiby", None, r"трубогиб", "NEW:trubogiby"),
    ("konteinery", None, r"контейнер", "yashchiki-sumki"),
    ("nasadki-miksera", None, r"насадка .{0,12}миксер", "str-miksery"),
    ("nasadki-payalnye", None, r"насадка ws-|насадка для пайки|насадка д/пайки", "NEW:nasadki-payalnye"),
    ("pily-lentochnye", None, r"пила ленточная", "NEW:pily-lentochnye"),
    ("ochistiteli", None, r"очиститель", "str-rastvoriteli"),
    ("krimpery", None, r"кримпер", "NEW:krimpery"),
    ("magnity", None, r"магнит", None),
    ("pressy", None, r"\bпресс\b", None),
    ("zazhimy", None, r"зажим", None),
    ("ventili", None, r"вентиль", None),
    ("tablichki", None, r"табличка", None),
    ("centry-tokarnye", None, r"\bцентр\b", None),
    ("opravki", None, r"оправка", None),
    ("kozhuhi", None, r"кожух", None),
    ("stanki", None, r"\bстанок\b", None),
    ("nasosy", 161, r"насос", None),
    ("kustorezy-parts", 183, r".", None),
    ("krugi-parts", 82, r".", None),
    ("sverla-parts", 81, r".", None),
    ("trimmery-parts", 181, r".", None),
    ("leska-cat-parts", 105, r".", None),
]

assigned = []
unassigned = []
for r in rows:
    name = r["name"].lower()
    hit = None
    for cluster, cat_id, pattern, cand in RULES:
        if cat_id is not None and r["cat_id"] != cat_id:
            continue
        if re.search(pattern, name):
            hit = (cluster, cand)
            break
    if hit:
        assigned.append((r, hit[0], hit[1]))
    else:
        unassigned.append(r)

cnt = Counter(cl for _, cl, _ in assigned)
print("== кластеры ==")
for cl, n in cnt.most_common():
    pub = sum(1 for r, c, _ in assigned if c == cl and r["pub"])
    cand = next(cd for _, c, cd in assigned if c == cl)
    print(f"{cl:24s} {n:4d} (pub {pub:4d})  → {cand}")
print()
print(f"== НЕ РАЗОБРАНО: {len(unassigned)} (pub {sum(1 for r in unassigned if r['pub'])}) ==")
fw = Counter(re.split(r"[\s,]+", r["name"].lower().strip())[0].strip('\"(') for r in unassigned)
print("первое слово топ-30:", fw.most_common(30))
with open("scratchpad/catalog/cat-07/unassigned.txt", "w", encoding="utf-8") as f:
    for r in unassigned:
        f.write(("P " if r["pub"] else "- ") + r["name"] + "\n")
