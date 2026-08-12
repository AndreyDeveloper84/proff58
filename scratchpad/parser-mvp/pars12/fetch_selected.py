"""Fetch selected shlifmashiny cards with throttle."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from parser.client import PoliteClient
from parser.product import parse_product

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
    ],
    "zubr": [
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/lentochnye-shlifovalnye-mashiny/zlshm-76-950-29s4/",
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/orbitalno-shlifovalnye-mashiny/zoshm-450-125-29s7/",
    ],
}

out_dir = Path("scratchpad/parser-mvp/pars12/cards")
client = PoliteClient(cache_dir=Path("scratchpad/parser-mvp/http-cache"), throttle_s=1.0)

try:
    for source, urls in URLS.items():
        for url in urls:
            try:
                html = client.get_text(url)
                card = parse_product(html, source, url)
                path = out_dir / f"{source}_{Path(url).name or Path(url).parent.name}.html"
                path.write_text(html, encoding="utf-8")
                print(f"OK {source}: {card.name}")
                for k, v in card.attributes.items():
                    print(f"   {k}: {v}")
            except Exception as exc:
                print(f"ERR {source} {url}: {exc}")
            time.sleep(1.0)
finally:
    client.close()
