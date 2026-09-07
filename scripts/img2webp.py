#!/usr/bin/env python3
"""JPEG/PNG → WebP для витрины.

Figma отдаёт только PNG/JPG/SVG/PDF — webp она не умеет, и это нормально:
конвертируем на нашей стороне. Оптимизатор Next выключен
(`images: { unoptimized: true }` в next.config), поэтому в репозиторий должен
попадать файл ровно того размера, в котором он показывается, — масштабировать
на лету некому.

    python scripts/img2webp.py вход.jpg --out frontend/public/info/hero.webp \
        --width 1600 --crop 16:9 --quality 82

Без `--crop` пропорции сохраняются. `--crop` вырезает по центру: сначала
подгоняется соотношение сторон, потом кадр ужимается до `--width`.
"""

from __future__ import annotations

import argparse
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageOps

# 82 — то, на чём останавливаются глазом: ниже появляются разводы на плашках
# инструмента, выше файл растёт без видимой разницы.
DEFAULT_QUALITY = 82


def parse_ratio(value: str) -> Fraction:
    """«16:9» → Fraction(16, 9)."""
    left, _, right = value.partition(":")
    if not right:
        raise argparse.ArgumentTypeError("пропорции задаются как «16:9»")
    return Fraction(int(left), int(right))


def center_crop(image: Image.Image, ratio: Fraction) -> Image.Image:
    """Вырезать по центру кадр с заданным соотношением сторон."""
    width, height = image.size
    target = float(ratio)
    if width / height > target:
        new_width = round(height * target)
        left = (width - new_width) // 2
        return image.crop((left, 0, left + new_width, height))
    new_height = round(width / target)
    top = (height - new_height) // 2
    return image.crop((0, top, width, top + new_height))


def convert(
    source: Path,
    destination: Path,
    width: int | None,
    ratio: Fraction | None,
    quality: int,
) -> tuple[int, int, int]:
    # Телефонные снимки приходят с EXIF-поворотом; без exif_transpose портрет
    # ляжет боком.
    image = ImageOps.exif_transpose(Image.open(source)).convert("RGB")
    if ratio is not None:
        image = center_crop(image, ratio)
    if width is not None and image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.LANCZOS)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "WEBP", quality=quality, method=6)
    return image.width, image.height, destination.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="исходный JPEG или PNG")
    parser.add_argument("--out", type=Path, required=True, help="куда положить .webp")
    parser.add_argument("--width", type=int, help="ширина в пикселях после кадрирования")
    parser.add_argument("--crop", type=parse_ratio, help="соотношение сторон, например 16:9")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error(f"нет файла {args.source}")

    width, height, size = convert(args.source, args.out, args.width, args.crop, args.quality)
    print(f"{args.out}  {width}x{height}  {size // 1024} КБ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
