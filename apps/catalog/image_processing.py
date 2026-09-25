"""Автообработка фото товара без нейросети (ADR-0014): чистые функции над байтами.

Открыть безопасно → понять фон по краю кадра → для белого фона и прозрачности
обрезать поля и вписать товар в белый квадрат 1200×1200.

Чёрный фон здесь не обрабатывается: без удаления фона нейросетью обрезка дала бы
тот же фон в квадрате, только крупнее. Такие фото получают статус «ждёт удаления
фона». Прочий фон (сцена, цветная подложка, карточка с характеристиками) не
обрабатывается вовсе — см. `image_autoprocess`. Проба на 292 фото стенда: белый
край — 56 %, чёрный — 14 %, прочий — 30 %.

Django здесь нет намеренно: модуль тестируется на синтетических картинках и не
знает ни про модели, ни про storage (это `image_autoprocess`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageOps, ImageStat

#: Версия параметров ниже. Поднять при любом их изменении — копии со старой версией
#: пересоздаст `process_product_images --outdated`.
PROCESSING_VERSION = 2

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

#: Товар в готовом квадрате меньше этой доли — исходник мелкий, копия на проверку.
#: На стенде (298 белых фото) порог отсеял 2 фото, товар на которых крошечный.
MIN_PRODUCT_SHARE = 0.5
FINGERPRINT_SIZE = 16  # отпечаток кадра — 16×16 = 256 бит
#: Кадры одного товара, отличающиеся не больше чем на столько бит, — один и тот же
#: снимок. Замер на 800 фото стенда: тот же снимок, пересжатый в JPEG и уменьшенный
#: или увеличенный, уходит на 1 бит в среднем и на 6 — в 99 % случаев; ближайшие
#: разные кадры одного товара (вид спереди и сзади) — 10 бит.
DUPLICATE_DISTANCE = 6

PIECE_GRID = 128  # сетка замера кусков; сторона квадрата ужимается до неё LANCZOS
#: Насколько пиксель сетки должен отличаться от белого, чтобы считаться содержимым.
#: Больше TRIM_TOLERANCE (12), которым режут поля по исходнику: после ужатия
#: до 128×128 края товара замыливаются, и слишком строгий порог рвёт тонкие детали.
PIECE_INK = 14
#: Копия, у которой самый большой кусок занимает меньше этой доли содержимого, —
#: разорванная. Замер на 67 копиях стенда (нейросеть, LANCZOS, 8-связность):
#: две съеденные карточки с текстом дали 0,30 и 0,58; худший цельный товар — 0,98,
#: медиана 1,00. 4-связность так не годится: тонкая штанга триммера рвётся (0,59).
MIN_PIECE_SHARE = 0.8


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
class Square:
    """Готовая витринная копия."""

    content: bytes  # WebP
    #: Товар занял меньше MIN_PRODUCT_SHARE квадрата даже после увеличения.
    small: bool
    #: Копия распалась на куски — так выглядит съеденная нейросетью карточка.
    #: Считается только там, где фон удаляли (`to_square(measure_pieces=True)`).
    torn: bool = False


@dataclass(frozen=True)
class Result:
    kind: str
    #: Копия; None — автоматически обработать нельзя (black/other/blank).
    square: Square | None
    #: Отпечаток исходного кадра — по нему ищутся одинаковые фото у товара.
    fingerprint: str = ""

    @property
    def content(self) -> bytes | None:
        return self.square.content if self.square else None


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


def _inner() -> int:
    return round(CANVAS * (1 - 2 * MARGIN))


def _scale(product: Image.Image) -> float:
    return min(_inner() / product.width, _inner() / product.height, MAX_UPSCALE)


def product_share(product: Image.Image) -> float:
    """Какую долю стороны квадрата (без полей) займёт товар после вписывания."""
    return max(product.width, product.height) * _scale(product) / _inner()


def fit_into_square(product: Image.Image) -> Image.Image:
    """Вписать уже обрезанный товар по центру белого квадрата."""
    scale = _scale(product)
    size = (max(1, round(product.width * scale)), max(1, round(product.height * scale)))
    product = product.resize(size, Image.LANCZOS)
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(product, ((CANVAS - size[0]) // 2, (CANVAS - size[1]) // 2))
    return canvas


def largest_piece_share(square: Image.Image) -> float:
    """Какую долю содержимого готового квадрата занимает самый большой его кусок.

    Цельный товар — одна фигура (доля около 1). Карточка, из которой нейросеть
    выела текст, распадается на обрывки букв и иконок, и доля падает.

    Считается на сетке PIECE_GRID (LANCZOS) обходом в ширину — не рекурсией:
    при 8-связности глубина легко превысила бы лимит интерпретатора.
    """
    grid = PIECE_GRID
    px = square.convert("RGB").resize((grid, grid), Image.LANCZOS).load()
    ink = {
        y * grid + x for y in range(grid) for x in range(grid) if 255 - min(px[x, y]) > PIECE_INK
    }
    if not ink:
        return 0.0
    total, biggest = len(ink), 0
    while ink:
        stack, size = [ink.pop()], 0
        while stack:
            y, x = divmod(stack.pop(), grid)
            size += 1
            for ny in (y - 1, y, y + 1):
                for nx in (x - 1, x, x + 1):
                    if 0 <= ny < grid and 0 <= nx < grid:
                        neighbour = ny * grid + nx
                        if neighbour in ink:
                            ink.discard(neighbour)
                            stack.append(neighbour)
        biggest = max(biggest, size)
    return biggest / total


def to_square(product: Image.Image, *, measure_pieces: bool = False) -> Square:
    """Обрезанный товар на белом → WebP витринной копии и признаки «мелкое», «рвань».

    `measure_pieces` включают там, где фон удаляла нейросеть: только она способна
    разорвать кадр. Обрезка полей куски не создаёт, а замер стоит ~0,1 с на фото.
    """
    canvas = fit_into_square(product)
    buf = io.BytesIO()
    canvas.save(buf, format="WEBP", quality=QUALITY)
    return Square(
        content=buf.getvalue(),
        small=product_share(product) < MIN_PRODUCT_SHARE,
        torn=measure_pieces and largest_piece_share(canvas) < MIN_PIECE_SHARE,
    )


def fingerprint(rgb: Image.Image) -> str:
    """Разностный хэш кадра (dHash): одинаковые снимки разного размера и сжатия
    дают отпечатки, отличающиеся на считанные биты."""
    n = FINGERPRINT_SIZE
    gray = rgb.convert("L").resize((n + 1, n), Image.LANCZOS)
    px = gray.load()
    bits = 0
    for y in range(n):
        for x in range(n):
            bits = bits << 1 | (px[x, y] > px[x + 1, y])
    return f"{bits:0{n * n // 4}x}"


def fingerprint_distance(a: str, b: str) -> int:
    return (int(a, 16) ^ int(b, 16)).bit_count()


def is_duplicate(a: str, b: str) -> bool:
    return bool(a and b) and fingerprint_distance(a, b) <= DUPLICATE_DISTANCE


def process(raw: bytes) -> Result:
    """Байты исходника → витринная копия (или None, если автоматически нельзя)."""
    img = open_image(raw)
    kind = classify(img)
    rgb = flatten_on_white(img) if kind == ImageKind.ALPHA else img.convert("RGB")
    mark = fingerprint(rgb)
    if kind not in (ImageKind.ALPHA, ImageKind.WHITE):
        return Result(kind=kind, square=None, fingerprint=mark)
    bbox = content_bbox(rgb)
    if bbox is None:
        return Result(kind=ImageKind.BLANK, square=None, fingerprint=mark)
    return Result(kind=kind, square=to_square(rgb.crop(bbox)), fingerprint=mark)
