"""Phase 8 · ступень 1 — генерация испорченных артефактов негативной матрицы.

Все файлы пишутся в ВРЕМЕННЫЙ каталог (scratchpad/phase8/tmp-negatives),
не в var/catalog-processing/inbox: контрактный inbox не должен содержать
заведомо битых файлов.

Usage: uv run python scratchpad/phase8/make_negatives.py <run_id>
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
INBOX = BASE / "var" / "catalog-processing" / "inbox"
TMP = Path(__file__).resolve().parent / "tmp-negatives"

FOREIGN_UUID = "00000000-dead-4bee-8000-000000000001"
FAKE_HASH = "f" * 64


def main() -> None:
    run_id = sys.argv[1]
    TMP.mkdir(parents=True, exist_ok=True)
    good = json.loads((INBOX / f"{run_id}.result.json").read_text(encoding="utf-8"))

    def dump(name: str, data: dict | str) -> None:
        path = TMP / name
        if isinstance(data, str):
            path.write_text(data, encoding="utf-8")
        else:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        print(f"{name}")

    # Эталонная копия во временном каталоге (контроль: сам путь не ломает импорт).
    dump(f"{run_id}.result.json", good)

    # N1 — битый JSON.
    dump("n1-broken.result.json", '{"schema_version": "1.0", "items": [')

    # N2 — не проходит JSON Schema (нет обязательного items, лишнее поле).
    n2 = copy.deepcopy(good)
    n2.pop("items")
    n2["unexpected_field"] = "PH8-SYN"
    dump("n2-schema.result.json", n2)

    # N3b — имя файла не совпадает с run_id внутри JSON (сам JSON валиден).
    dump(f"{FOREIGN_UUID}.result.json", good)

    # N4 — несуществующий/чужой batch.
    n4 = copy.deepcopy(good)
    n4["run_id"] = FOREIGN_UUID
    dump("n4-foreign-run.result.json", n4)

    # N5 — tool_type вне canonical manifest (валидный по pattern, нет в словаре).
    n5 = copy.deepcopy(good)
    n5["items"][0]["changes"][0]["proposed_value"]["option_slug"] = "ph8-syn-fake-tool-type"
    dump("n5-unknown-option.result.json", n5)

    # N5b — option_slug нарушает pattern схемы.
    n5b = copy.deepcopy(good)
    n5b["items"][0]["changes"][0]["proposed_value"]["option_slug"] = "PH8_SYN_UPPER"
    dump("n5b-bad-slug-pattern.result.json", n5b)

    # N6 — product_ref, которого нет в batch (свидетель PH8-SYN-006).
    n6 = copy.deepcopy(good)
    n6["items"] = [copy.deepcopy(good["items"][0])]
    n6["items"][0]["product_ref"] = 6
    dump("n6-ref-outside-batch.result.json", n6)

    # N13 — export_checksum не совпадает с последним export.
    n13 = copy.deepcopy(good)
    n13["export_checksum"] = FAKE_HASH
    dump("n13-export-checksum.result.json", n13)

    # N14 — taxonomy_hash не совпадает.
    n14 = copy.deepcopy(good)
    n14["taxonomy_hash"] = FAKE_HASH
    dump("n14-taxonomy-hash.result.json", n14)

    # N15 — input_hash item не совпадает со снимком.
    n15 = copy.deepcopy(good)
    n15["items"][0]["input_hash"] = FAKE_HASH
    dump("n15-input-hash.result.json", n15)

    # N16 — changes при identity.status != matched.
    n16 = copy.deepcopy(good)
    n16["items"][0]["identity"]["status"] = "partial"
    dump("n16-changes-without-identity.result.json", n16)


if __name__ == "__main__":
    main()
