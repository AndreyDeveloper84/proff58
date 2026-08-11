"""Phase 8 · ступень 3 — модерация findings run 00638eaa.

Решения модератора по итогам ручной сверки evidence (см. протокол,
таблицу сверки): approve — предложение верно и evidence подтверждены;
reject — предложенный тип не покрывает товар.

Запуск: manage.py shell -c "exec(open('scratchpad/phase8/moderate_step3.py', encoding='utf-8').read())"
"""

from apps.catalog.models import CatalogChange
from apps.catalog.processing import review_catalog_change

RUN_ID = "00638eaa-0d7e-4532-b13f-ab40b3b8be0d"
REVIEWER_ID = 1

DECISIONS = {
    # product_ref: (decision, comment)
    4: ("approved", "Ареометр АНТ-1 710-770 ГОСТ — тип izm-areometry точен; evidence сверены."),
    22: ("approved", "Ручной гайковёрт РГ56М — точного типа нет; spetsialnye-klyuchi "
         "приемлем как ближайший (специальный шиномонтажный ключ)."),
    123: ("approved", "ДК-5(В) — кабельный домкрат, evidence производителя КВТ сверены."),
    164: ("approved", "Орион PW-325 — ЗУ для АКБ, evidence производителя сверены."),
    179: ("approved", "АСО К-11 — поршневой компрессор, evidence завода сверены."),
    377: ("approved", "Сервис Ключ 72570 — шарошки, точный артикул, evidence сверены."),
    422: ("approved", "DENZEL RB180-36 (59610) — воздуходувка, evidence дилера сверены."),
    4944: ("approved", "ALVE multi box 3003 — бокс-органайзер на лестницу, evidence сверены."),
    4945: ("approved", "Винт ГОСТ Р ИСО 4017 М8х30 — krep-bolty, evidence сверены."),
    6798: ("rejected", "Катод плазмотрона ≠ сопло: value svar-sopla («Сопла, мундштуки, "
           "наконечники») катоды не покрывает; нужен отдельный тип расходки плазмы."),
    11232: ("approved", "REXANT 12-0621 — одиночный паяльник (не станция), evidence сверены."),
    23606: ("approved", "Стиральный порошок SP plus 3кг — hoz-himiya верно по сути; "
         "identity косвенная (опечатка), но evidence подтверждена ручной сверкой."),
}

changes = {c.product_ref: c for c in CatalogChange.objects.filter(item__run_id=RUN_ID)}
print("changes in run:", len(changes))

for ref, (decision, comment) in sorted(DECISIONS.items()):
    c = changes[ref]
    res = review_catalog_change(c.id, decision, REVIEWER_ID, comment)
    print(f"ref={ref:6d} {c.proposed_value} -> {decision:9s} | result={res.status}")
