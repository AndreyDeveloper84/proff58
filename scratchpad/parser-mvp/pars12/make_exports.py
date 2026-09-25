"""Create parser export JSON files from saved HTML cards."""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from parser.product import parse_product

CARD_DIR = PROJECT_ROOT / 'scratchpad/parser-mvp/pars12/cards'
OUT_DIR = PROJECT_ROOT / 'scratchpad/parser-mvp/pars12/exports'
OUT_DIR.mkdir(exist_ok=True)

SOURCE_CATEGORY = {
    "resanta": ("Шлифовальные машины Ресанта", "https://resanta.ru/sitemap-shop.xml"),
    "vihr": ("Шлифовальные машины Вихрь", "https://vihr.su/sitemap-shop.xml"),
    "interskol": ("Шлифовальные машины Интерскол", "https://www.interskol.ru/sitemap.xml"),
    "zubr": ("Шлифовальные машины ЗУБР", "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/"),
}

URLS = {
    "resanta": [
        "https://resanta.ru/lentochnaya-shlifovalnaya-mashina-lshm-75-900-resanta/",
        "https://resanta.ru/ekstsentrikovaya-shlifovalnaya-mashina-resanta-eshm-125-5e/",
    ],
    "vihr": [
        "https://vihr.su/lentochnaya-shlifovalnaya-mashina-vihr-lshm-75-800/",
        "https://vihr.su/vibroshlifovalnaya-mashina-vihr-vshm-115e/",
        "https://vihr.su/ekstsentrikovaya-shlifovalnaya-mashina-vikhr-eshm-125-5e/",
    ],
    "interskol": [
        "https://www.interskol.ru/product/lentochnoshlifoval-naya-mashina-interskol-lshm-100-1200e-interskol",
        "https://www.interskol.ru/product/ploskoshlifoval-naya-mashina-interskol-pshm-104-220-interskol",
        "https://www.interskol.ru/product/ekscentrikovaya-shlifoval-naya-mashina-interskol-eshm-125-270e-interskol",
        "https://www.interskol.ru/product/pryamoshlifoval-naya-mashina-s-besschetochnym-ventil-nym-dvigatelem-interskol-pshm-8-18ve-interskol",
        "https://www.interskol.ru/product/besschetochnaya-ploskoshlifoval-naya-mashina-interskol-pshm-100-350e-3-0",
    ],
    "zubr": [
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/lentochnye-shlifovalnye-mashiny/zlshm-76-950-29s4/",
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/orbitalno-shlifovalnye-mashiny/zoshm-450-125-29s7/",
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/ploskoshlifovalnye-mashiny/zpshm-300e-02-29s6/",
    ],
}

def url_key(url: str) -> str:
    p = Path(url)
    if p.name:
        return p.name
    return Path(url.rstrip('/')).name

products_by_source: dict[str, list] = {}

for source, urls in URLS.items():
    for url in urls:
        key = url_key(url)
        html_path = CARD_DIR / f"{source}_{key}.html"
        if not html_path.exists():
            print(f"MISSING {html_path}")
            continue
        html = html_path.read_text(encoding='utf-8')
        try:
            card = parse_product(html, source, url)
        except Exception as exc:
            print(f"SKIP {source} {url}: {exc}")
            continue
        products_by_source.setdefault(source, []).append({
            "source_url": card.source_url,
            "name": card.name,
            "brand": card.brand,
            "manufacturer_sku": card.manufacturer_sku,
            "description": card.description,
            "attributes": card.attributes,
            "summary_raw": card.summary_raw,
        })
        print(f"OK {source}: {card.name}")

for source, products in products_by_source.items():
    cat_name, cat_url = SOURCE_CATEGORY[source]
    export = {
        "schema_version": "1.0",
        "source": source,
        "created_at": datetime.now(UTC).isoformat(),
        "category": {"name": cat_name, "source_url": cat_url},
        "products": products,
    }
    out_path = OUT_DIR / f"{source}.products.json"
    out_path.write_text(json.dumps(export, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"WROTE {out_path}: {len(products)} products")
