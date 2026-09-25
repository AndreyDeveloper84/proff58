#!/usr/bin/env python3
"""Фото товара → картинка для плитки типа инструмента (DRF-996).

Плитка навигации показывает предмет на 56×56 внутри карточки. Каталожное фото для
этого не годится как есть: оно снято на белом фоне, поэтому в тёмной теме на месте
картинки светится белый прямоугольник, а сам инструмент занимает половину кадра.

Скрипт делает три вещи:

1. **Убирает фон** заливкой от краёв, а не порогом по яркости. Порог съел бы и
   светлые части самого инструмента (у болгарки корпус почти белый); заливка от
   границы трогает только тот фон, что связан с краем кадра.
2. **Обрезает по предмету** — поля в исходнике съедали бы и без того маленькую
   плитку.
3. **Кладёт в квадрат** с небольшим полем, чтобы вытянутая пила и компактный гравер
   выглядели в сетке одинаково крупно.

    python scripts/tool_type_tile.py фото.webp --out frontend/public/catalog/tool-types/pily.webp
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

#: Насколько цвет пикселя может отличаться от белого, чтобы считаться фоном.
#:
#: Единица измерения не очевидна: Pillow складывает отличие ПО ВСЕМ каналам, а не
#: берёт максимум по одному. Поэтому серая подложка съёмки (220, 220, 222) — это не
#: «35», а 3 × 35 = 105, и порог вроде 40 не убирает ничего, кроме чистого белого.
#: 112 выбран между двумя фактами каталожных фото: подложка — 105, самый светлый
#: корпус инструмента (214) — 123. Выше 120 начинает съедать сам инструмент.
BACKGROUND_TOLERANCE = 112
#: Сторона готовой плитки. 224 = 56 CSS-пикселей при плотности 4×.
TILE_SIZE = 224
#: Поле вокруг предмета, чтобы он не упирался в край карточки.
PADDING = 8


def _border_points(width: int, height: int, step: int) -> list[tuple[int, int]]:
    """Точки по всему периметру кадра, а не только углы.

    Фон у каталожных фото не ровно белый: подложка бывает пятнистой, со швом или
    тенью, и заливка из четырёх углов оставляет светлый прямоугольник — в тёмной
    теме он виден как белая плашка вокруг инструмента. Заходим с каждой стороны
    много раз, поэтому разорванный фон вычищается целиком.
    """
    points = []
    for x in range(0, width, step):
        points += [(x, 0), (x, height - 1)]
    for y in range(0, height, step):
        points += [(0, y), (width - 1, y)]
    return points


def drop_background(image: Image.Image, tolerance: int) -> Image.Image:
    """Сделать прозрачным фон, связанный с краями кадра."""
    rgba = image.convert("RGBA")
    width, height = rgba.size
    pixels = rgba.load()
    for point in _border_points(width, height, step=4):
        if pixels[point][3] == 0:
            continue  # уже вычищено предыдущей заливкой
        ImageDraw.floodfill(rgba, point, (0, 0, 0, 0), thresh=tolerance)
    return rgba


def fit_square(image: Image.Image, size: int, padding: int) -> Image.Image:
    """Обрезать по предмету и вписать в квадрат, сохранив пропорции."""
    box = image.getbbox()
    if box:
        image = image.crop(box)
    inner = size - padding * 2
    image.thumbnail((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(image, ((size - image.width) // 2, (size - image.height) // 2), image)
    return canvas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--size", type=int, default=TILE_SIZE)
    parser.add_argument("--padding", type=int, default=PADDING)
    parser.add_argument("--tolerance", type=int, default=BACKGROUND_TOLERANCE)
    args = parser.parse_args()

    if not args.source.is_file():
        parser.error(f"нет файла {args.source}")

    tile = fit_square(
        drop_background(Image.open(args.source), args.tolerance), args.size, args.padding
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tile.save(args.out, "WEBP", quality=88, method=6)
    print(f"{args.out}  {tile.width}x{tile.height}  {args.out.stat().st_size // 1024} КБ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
