"""Контролёр качества витринных копий: признаки → решение accept/reject/review.

Разделяет то, что уже умеет `image_processing` (обрезка полей, отпечаток, связность
после нейросети), от вопроса «можно ли показать эту копию без человека». Чистые
функции — Django, storage и модели сюда не заходят.

Три решения контролёра (`Decision.decision`):

- ``AUTO_ACCEPT`` — уверенно пригодная копия: обязательные проверки маршрута пройдены,
  блокирующих признаков нет;
- ``AUTO_REJECT_CANDIDATE`` — только достоверный технический брак: результат пуст
  (нейросеть/обрезка не нашли товар на снимке). Разорванная нейросетью карточка,
  дубль, мелкое фото и подозрение на грязный фон — это ``NEEDS_REVIEW``, не отказ:
  различие явно требует задание (§5.4), у них слишком много ложных срабатываний
  для автоматического удаления кандидата;
- ``NEEDS_REVIEW`` — остальное: касание края, подозрение на подложку, дубль, мелкое
  или сильно увеличенное фото, разорванная вырезка, непроверенный маршрут
  (``rembg_manual``), неподтверждённая пригодность известного не-товарного кадра.

Эвристика подозрения на подложку (``pale_content_share``) подобрана на пяти реальных
файлах аудита 24.09.2026 (`docs/catalog/2026-09-24-photo-quality-pilot.md`): доля
пикселей содержимого готового квадрата, которые отличаются от чистого белого, но
остаются светлыми (средняя яркость > 200). У чистого предметного кадра (Hanskonner,
ЗУБР) она держится у 0,04–0,05; у грязной подложки ВИХРЯ и рекламного плаката с
текстом на белых полях — 0,14–0,19. Порог 0,10 разделяет оба случая с запасом на
этой выборке, но не обещан для всего каталога — при слабых сигналах решение всегда
``NEEDS_REVIEW``, никогда молчаливое принятие.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image

from . import image_processing

#: Версия правил контролёра. Поднимать при изменении порогов/набора причин —
#: `process_product_images --redecide` пересчитывает решение по сохранённым
#: признакам (`qc_features`), не трогая файл и не вызывая нейросеть повторно.
QC_RULES_VERSION = 1

PALE_GRID = 256  # сторона, до которой ужимается готовый квадрат для замера подложки
#: Порог доли «бледного, но не белого» содержимого — см. докстринг модуля.
PALE_SHARE_MAX = 0.10
#: Минимум пикселей содержимого в сетке замера, чтобы доверять доле (иначе шум).
PALE_MIN_CONTENT_PX = 200
EDGE_TOUCH_TOLERANCE = 2  # px — антиалиасинг у самого края не считаем касанием


class Route:
    """Каким путём получена копия — от этого зависит, каким проверкам она подчиняется."""

    TRIM = "trim"
    REMBG_BLACK = "rembg_black"
    #: Точечное действие «Предметное фото: подготовить удаление фона» — маршрут не
    #: проверен на независимой выборке, поэтому никогда не даёт auto_accept (§5.3).
    REMBG_MANUAL = "rembg_manual"


class Decision:
    AUTO_ACCEPT = "auto_accept"
    AUTO_REJECT_CANDIDATE = "auto_reject_candidate"
    NEEDS_REVIEW = "needs_review"


class Reason:
    """Коды причин — попадают в `qc_reasons` и в текст вопроса менеджеру."""

    EMPTY = "empty"
    TOUCHES_EDGE = "touches_edge"
    SUSPECT_BACKDROP = "suspect_backdrop"
    SMALL = "small"
    TORN = "torn"
    DUPLICATE = "duplicate"
    UNPROVEN_ROUTE = "unproven_route"
    UNKNOWN_PURPOSE_ON_COMPLEX_BG = "unknown_purpose_on_complex_bg"


#: Русский текст причины — админка и отчёты берут отсюда, чтобы не плодить копии строк.
REASON_LABELS = {
    Reason.EMPTY: "Товар на фото не найден",
    Reason.TOUCHES_EDGE: "Товар касается края кадра — не проверено, что ничего не обрезано",
    Reason.SUSPECT_BACKDROP: "Похоже на пятнистую/цветную подложку внутри полей",
    Reason.SMALL: "Товар занимает меньше половины кадра даже после увеличения",
    Reason.TORN: "Нейросеть могла разорвать изображение на куски",
    Reason.DUPLICATE: "Такой же кадр у товара уже есть",
    Reason.UNPROVEN_ROUTE: "Ручное удаление фона — маршрут ещё не проверен на выборке",
    Reason.UNKNOWN_PURPOSE_ON_COMPLEX_BG: "Не подтверждено, что это предметный кадр, а не сцена",
}


@dataclass(frozen=True)
class Features:
    """Измеренные признаки — хранятся как есть (`qc_features`), не сворачиваются в балл."""

    source_width: int
    source_height: int
    content_width: int
    content_height: int
    touches_edge: bool
    product_share: float  # доля стороны холста, которую займёт товар (image_processing)
    small: bool
    torn: bool
    pale_content_share: float | None  # None — признак не считался (нет готового квадрата)
    suspect_backdrop: bool

    def to_dict(self) -> dict:
        return {
            "source_width": self.source_width,
            "source_height": self.source_height,
            "content_width": self.content_width,
            "content_height": self.content_height,
            "touches_edge": self.touches_edge,
            "product_share": round(self.product_share, 4),
            "small": self.small,
            "torn": self.torn,
            "pale_content_share": (
                round(self.pale_content_share, 4) if self.pale_content_share is not None else None
            ),
            "suspect_backdrop": self.suspect_backdrop,
        }


@dataclass(frozen=True)
class Verdict:
    decision: str
    reasons: list[str] = field(default_factory=list)


def _touches_edge(source_size: tuple[int, int], bbox: tuple[int, int, int, int]) -> bool:
    w, h = source_size
    x0, y0, x1, y1 = bbox
    return (
        x0 <= EDGE_TOUCH_TOLERANCE
        or y0 <= EDGE_TOUCH_TOLERANCE
        or x1 >= w - EDGE_TOUCH_TOLERANCE
        or y1 >= h - EDGE_TOUCH_TOLERANCE
    )


def _pale_content_share(square_rgb: Image.Image) -> float | None:
    """Доля светлого-но-не-белого содержимого готового квадрата. См. докстринг модуля."""
    bbox = image_processing.content_bbox(square_rgb)
    if bbox is None:
        return None
    crop = square_rgb.crop(bbox)
    w, h = crop.size
    scale = min(1.0, PALE_GRID / max(w, h))
    if scale < 1.0:
        crop = crop.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
    px = crop.load()
    cw, ch = crop.size
    total = pale = 0
    for y in range(ch):
        for x in range(cw):
            r, g, b = px[x, y]
            if 255 - min(r, g, b) <= image_processing.TRIM_TOLERANCE:
                continue
            total += 1
            if (r + g + b) / 3 > 200:
                pale += 1
    if total < PALE_MIN_CONTENT_PX:
        return None
    return pale / total


def analyze(
    *,
    source_size: tuple[int, int],
    content_bbox: tuple[int, int, int, int] | None,
    square: image_processing.Square | None,
    square_rgb: Image.Image | None,
    product_share: float = 0.0,
) -> Features:
    """Собрать признаки кандидата. `square_rgb` — декодированный готовый квадрат
    (для подсчёта `pale_content_share`); можно не передавать, если его нет под рукой
    ещё раз — тогда признак останется `None` и на решение не повлияет."""
    sw, sh = source_size
    if content_bbox is None:
        cw = ch = 0
        touches = False
    else:
        x0, y0, x1, y1 = content_bbox
        cw, ch = x1 - x0, y1 - y0
        touches = _touches_edge(source_size, content_bbox)
    pale_share = _pale_content_share(square_rgb) if square_rgb is not None else None
    return Features(
        source_width=sw,
        source_height=sh,
        content_width=cw,
        content_height=ch,
        touches_edge=touches,
        product_share=product_share,
        small=bool(square and square.small),
        torn=bool(square and square.torn),
        pale_content_share=pale_share,
        suspect_backdrop=bool(pale_share is not None and pale_share > PALE_SHARE_MAX),
    )


def decide(
    features: Features,
    *,
    route: str,
    is_duplicate: bool,
    is_empty: bool,
    purpose_confirmed_subject: bool,
) -> Verdict:
    """Три решения контролёра.

    `auto_accept` здесь не означает «сразу на витрину»: маршрут ещё должен быть в
    `PRODUCT_IMAGE_AUTO_ACCEPT_ROUTES` — это решает вызывающий код (`image_autoprocess`),
    переводя непроверенный маршрут в режим наблюдения (`observed`) вместо публикации.
    """
    if is_empty:
        return Verdict(Decision.AUTO_REJECT_CANDIDATE, [Reason.EMPTY])

    reasons: list[str] = []
    if is_duplicate:
        reasons.append(Reason.DUPLICATE)
    if features.touches_edge:
        reasons.append(Reason.TOUCHES_EDGE)
    if features.suspect_backdrop:
        reasons.append(Reason.SUSPECT_BACKDROP)
    if features.torn:
        reasons.append(Reason.TORN)
    if features.small:
        reasons.append(Reason.SMALL)
    if route == Route.REMBG_MANUAL:
        reasons.append(Reason.UNPROVEN_ROUTE)
        if not purpose_confirmed_subject:
            reasons.append(Reason.UNKNOWN_PURPOSE_ON_COMPLEX_BG)

    if reasons:
        return Verdict(Decision.NEEDS_REVIEW, reasons)
    return Verdict(Decision.AUTO_ACCEPT, reasons)
