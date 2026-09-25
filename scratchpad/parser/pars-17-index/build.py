"""ПАРС-17: сборка read-only замеров покрытия индекса каталога.

    uv run python scratchpad/parser/pars-17-index/build.py <каталог с izo07-cards-*.jsonl>
    ssh taximeter@dev.proff58.ru \
        'docker exec -i proff58_staging-web-1 python manage.py shell' < p17_diag7.py

Собирает самодостаточные скрипты `p17_diag<N>.py`: общая шапка + корпус карточек
resanta.ru / vihr.su (ИЗО-07, только `status == 200` и непустой `sku`) + тело замера.
Замеры только читают БД.

  diag1 — сколько товаров скоупа не попадает в индекс и почему;
  diag2 — сверка артикулов каталога с SKU карточек без брендового токена;
  diag3 — реальный матчинг по скоупам + разбор not_found;
  diag5 — потенциал артикула из названия товара;
  diag6 — индекс по всему каталогу против индекса по скоупу карты;
  diag7 — ДО/ПОСЛЕ правки ПАРС-17 (сам по себе не меняет БД).

`p17_diag1.py` и `p17_diag4.py` карточек не требуют и лежат готовыми.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
SOURCES = {"resanta": "izo07-cards-resanta.jsonl", "vihr": "izo07-cards-vihr.jsonl"}
BODIES = ["diag2_tail.py", "diag3_tail.py", "diag5_tail.py", "diag6_tail.py", "diag7_tail.py"]


def main(cards_dir: Path) -> None:
    corpus = {}
    for source, fname in SOURCES.items():
        rows = [json.loads(line) for line in (cards_dir / fname).read_text("utf-8").splitlines()]
        corpus[source] = [
            {"sku": r["sku"], "name": (r.get("ld_name") or "").strip()}
            for r in rows
            if r.get("status") == 200 and r.get("sku")
        ]
    print({k: len(v) for k, v in corpus.items()})

    head = (HERE / "diag2_head.py").read_text("utf-8")
    cards = "CARDS = " + json.dumps(corpus, ensure_ascii=True) + "\n\n"
    for body in BODIES:
        n = body.split("_")[0].replace("diag", "")
        out = HERE / f"p17_diag{n}.py"
        out.write_text(head + cards + (HERE / body).read_text("utf-8"), encoding="utf-8")
        print("built", out.name)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "scratchpad/izo"))
