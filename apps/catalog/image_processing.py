"""Автообработка фото товара без нейросети (ADR-0014): чистые функции над байтами.

Открыть безопасно → понять фон по краю кадра → для белого фона и прозрачности
обрезать поля и вписать товар в белый квадрат 1200×1200.

Чёрный и прочий фон (сцена, серый, цветной) здесь не обрабатываются: без удаления
фона нейросетью обрезка дала бы тот же фон в квадрате, только крупнее. Такие фото
получают статус «ждёт удаления фона». Проба на 292 фото стенда: белый край — 56 %,
чёрный — 14 %, прочий — 30 %.

Django здесь нет намеренно: модуль тестируется на синтетических картинках и не
знает ни про модели, ни про storage (это `image_autoprocess`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageOps, ImageStat

#: Версия параметров ниже. Поднять при любом их изменении — копии со старой версией
#: пересоздаст `process_product_images --outdated`.
PROCESSING_VERSION = 1

CANVAS = 1200  # сторона белого квадрата
MARGIN = 0.07  # поля — доля стороны холста
MAX_UPSCALE = 2.0  # мелкий исходник не раздуваем сильнее — будет мыло
QUALITY = 85  # WebP, как у ImagePipeline
MAX_PIXELS = 40_000_000  # потолок против decompression bomb, как у ImagePipeline

EDGE_BACKGROUND_SHARE = 0.5  # фон — если им занята хотя бы половина рамки кадра
NEAR_WHITE = 240  # все каналы не темнее — пиксель рамки «белый»
NEAR_BLACK = 15  # все каналы не светлее — пиксель рамки «чёрный»
BORDER_UNIFORM_STD = 6.0  # сторона кадра однотонная, если разброс яркости меньше
WHITE_MIN = 245  # однотонная сторона светлее — белая, иначе это подложка другого цвета
BLACK_MAX = 8  # однотонная сторона темнее — чёрная (так выглядит потерянная прозрачность)
TRANSPARENT_EDGE_ALPHA = 128  # средняя альфа края ниже — фон прозрачный
TRIM_TOLERANCE = 12  # пиксель ближе к белому — фон; запас на шум JPEG


class ImageKind:
    WHITE = "white"
    BLACK = "black"
    OTHER = "other"
    ALPHA = "alpha"
    #: После обрезки не осталось ничего, кроме белого: показывать такое нельзя.
    BLANK = "blank"


class UnreadableImage(Exception):
    """Байты не удалось безопасно открыть как картинку."""


@dataclass(frozen=True)
class Result:
    kind: str
    #: WebP витринной копии; None — автоматически обработать нельзя (black/other/blank).
    content: bytes | None


def open_image(raw: bytes) -> Image.Image:
    """Открыть с защитой от бомб, повернуть по EXIF, первый кадр у анимации.

    Глобальный ``Image.MAX_IMAGE_PIXELS`` не трогаем: размер сверяем по заголовку
    сами, а встроенная защита Pillow остаётся вторым рубежом.
    """
    try:
        img = Image.open(io.BytesIO(raw))
        if img.width * img.height > MAX_PIXELS:  # по заголовку, до декодирования
            raise UnreadableImage(f"слишком большая картинка: {img.width}×{img.height}")
        img.seek(0)
        img.load()
        img = ImageOps.exif_transpose(img)
    except (OSError, ValueError, EOFError, Image.DecompressionBombError) as exc:
        raise UnreadableImage(str(exc)) from exc
    if img.mode in ("I", "I;16", "I;16B", "I;16L"):
        # convert("RGB") обрезает всё выше 255 до белого: 16-битный серый PNG
        # превратился бы в пустой белый квадрат. Сначала сжимаем шкалу до 8 бит.
        img = img.convert("I")
        if img.getextrema()[1] > 255:
            img = img.point(lambda v: v * (255 / 65535))
        img = img.convert("L")
    elif img.mode not in ("RGB", "RGBA", "LA", "PA", "P", "L"):
        img = img.convert("RGB")  # CMYK и прочие режимы
    return img


def _border_strips(img: Image.Image) -> list[Image.Image]:
    w, h = img.size
    band = max(1, min(w, h) // 50)
    return [
        img.crop((0, 0, w, band)),
        img.crop((0, h - band, w, h)),
        img.crop((0, 0, band, h)),
        img.crop((w - band, 0, w, h)),
    ]


def has_transparent_background(img: Image.Image) -> bool:
    """Прозрачен ли именно фон — край кадра, а не пара пикселей внутри."""
    if img.mode not in ("RGBA", "LA", "PA") and not (
        img.mode == "P" and "transparency" in img.info
    ):
        return False
    alpha = img.convert("RGBA").getchannel("A")
    edge = [ImageStat.Stat(s).mean[0] for s in _border_strips(alpha)]
    return sum(edge) / len(edge) < TRANSPARENT_EDGE_ALPHA


def _share(masks: list[Image.Image], total: int) -> float:
    return sum(m.histogram()[255] for m in masks) / total


def _solid_side_off(stats: list[ImageStat.Stat], low: float, high: float) -> bool:
    """Есть ли однотонная сторона не цвета фона — серый пол, цветная подложка."""
    return any(
        sum(s.stddev) / 3 < BORDER_UNIFORM_STD and not low <= sum(s.mean) / 3 <= high for s in stats
    )


def classify(img: Image.Image) -> str:
    """Тип фона по рамке кадра.

    Фон — это большинство пикселей рамки, а не «все четыре стороны однотонные»: у
    широкого товара (ключ, болторез, карточка во всю высоту) край кадра пересекает сам
    товар. Строгая проверка сторон отправляла такой белый фон к нейросети — на стенде
    71 из 100 «прочих» фото были именно такими (16.09.2026), а нейросеть портит текст.

    Однотонная сторона другого цвета — серый пол, цветная подложка — оставляет фото
    «прочим»: обрезка полей оставила бы её в квадрате.
    """
    if has_transparent_background(img):
        return ImageKind.ALPHA
    strips = _border_strips(img.convert("RGB"))
    total = sum(s.width * s.height for s in strips)
    channels = [s.split() for s in strips]
    darkest = [ImageChops.darker(ImageChops.darker(r, g), b) for r, g, b in channels]
    brightest = [ImageChops.lighter(ImageChops.lighter(r, g), b) for r, g, b in channels]
    white = _share([m.point(lambda v: 255 if v >= NEAR_WHITE else 0) for m in darkest], total)
    black = _share([m.point(lambda v: 255 if v <= NEAR_BLACK else 0) for m in brightest], total)
    stats = [ImageStat.Stat(s) for s in strips]
    if white >= EDGE_BACKGROUND_SHARE and not _solid_side_off(stats, WHITE_MIN, 255):
        return ImageKind.WHITE
    if black >= EDGE_BACKGROUND_SHARE and not _solid_side_off(stats, 0, BLACK_MAX):
        return ImageKind.BLACK
    return ImageKind.OTHER


def flatten_on_white(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    canvas = Image.new("RGB", rgba.size, (255, 255, 255))
    canvas.paste(rgba, mask=rgba.getchannel("A"))
    return canvas


def content_bbox(rgb: Image.Image) -> tuple[int, int, int, int] | None:
    """Рамка всего, что не белое; None — картинка целиком белая."""
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255)))
    r, g, b = diff.split()
    # максимум по каналам: бледно-жёлтый пиксель не должен уйти в фон по средней яркости
    mask = ImageChops.lighter(ImageChops.lighter(r, g), b).point(
        lambda v: 255 if v > TRIM_TOLERANCE else 0
    )
    return mask.getbbox()


def fit_into_square(product: Image.Image) -> Image.Image:
    """Вписать уже обрезанный товар по центру белого квадрата."""
    inner = round(CANVAS * (1 - 2 * MARGIN))
    scale = min(inner / product.width, inner / product.height, MAX_UPSCALE)
    size = (max(1, round(product.width * scale)), max(1, round(product.height * scale)))
    product = product.resize(size, Image.LANCZOS)
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(product, ((CANVAS - size[0]) // 2, (CANVAS - size[1]) // 2))
    return canvas


def process(raw: bytes) -> Result:
    """Байты исходника → витринная копия (или None, если автоматически нельзя)."""
    img = open_image(raw)
    kind = classify(img)
    if kind == ImageKind.ALPHA:
        rgb = flatten_on_white(img)
    elif kind == ImageKind.WHITE:
        rgb = img.convert("RGB")
    else:
        return Result(kind=kind, content=None)
    bbox = content_bbox(rgb)
    if bbox is None:
        return Result(kind=ImageKind.BLANK, content=None)
    buf = io.BytesIO()
    fit_into_square(rgb.crop(bbox)).save(buf, format="WEBP", quality=QUALITY)
    return Result(kind=kind, content=buf.getvalue())
