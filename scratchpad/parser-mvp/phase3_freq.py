"""Phase 3: частотный анализ полей выгрузки Phase 2 (32 карточки, 4 источника).

Read-only. Печатает по каждому источнику: поле, частота, примеры значений.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).parent / "output"
FILES = {
    "resanta": OUT / "resanta.products.json",
    "vihr": OUT / "vihr.products.json",
    "interskol": OUT / "interskol.products.json",
    "zubr": OUT / "zubr.products.json",
}

def main() -> None:
    for source, path in FILES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        products = data["products"]
        freq: Counter[str] = Counter()
        examples: dict[str, list[str]] = defaultdict(list)
        for p in products:
            for key, val in p["attributes"].items():
                freq[key] += 1
                if len(examples[key]) < 3 and val not in examples[key]:
                    examples[key].append(val)
        print(f"=== {source}: {len(products)} карточек, {len(freq)} уникальных полей ===")
        for key, count in freq.most_common():
            ex = " | ".join(examples[key])
            print(f"{count:3d}  {key}  =>  {ex}")
        print()

if __name__ == "__main__":
    main()
