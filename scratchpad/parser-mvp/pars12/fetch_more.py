import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from parser.client import PoliteClient
from parser.product import parse_product

URLS = {
    "zubr": [
        "https://zubr.ru/mekhanizirovannye-instrumenty/elektroinstrumenty/shlifovalnye-mashiny/ploskoshlifovalnye-mashiny/zpshm-300e-02-29s6/",
    ],
    "interskol": [
        "https://www.interskol.ru/product/besschetochnaya-ploskoshlifoval-naya-mashina-interskol-pshm-100-350e-3-0",
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
