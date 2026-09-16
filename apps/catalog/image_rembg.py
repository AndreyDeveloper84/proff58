"""Удаление фона нейросетью rembg (ADR-0014, итерация 2).

Для фото на чёрном и прочем фоне, которые без нейросети обработать нельзя.
Работает только в образе сервиса `celery-rembg` (`requirements/images.txt`): rembg
тянет onnxruntime, scipy, scikit-image, numba и opencv, поэтому в остальные образы
не ставится. Без него `is_available()` — False, и фото спокойно ждут сервис.

Цена на 2 ядрах: ~13 с на фото, пик памяти ~2,1 ГБ (smoke на 12 фото стенда,
Python 3.11, 16.09.2026). Модель одна на процесс и грузится при первом фото.
Чёрный фон — 6 из 6 чисто; рекламные карточки теряют часть текста.

Проба показала и слабое место: рекламные карточки с текстом нейросеть портит
(буквы уходят в фон). Поэтому результат для прочего фона идёт на проверку
менеджеру, а сразу на витрину — только чёрный фон (решение владельца 16.09.2026).
"""

from __future__ import annotations

import importlib.util
import io

from PIL import Image

from . import image_processing

MODEL = "isnet-general-use"
ALPHA_CUT = 24  # пиксели маски прозрачнее — фон, а не товар

_session = None


class RembgUnavailable(Exception):
    """rembg не установлен в этом образе."""


def is_available() -> bool:
    return importlib.util.find_spec("rembg") is not None


def cut_out(img: Image.Image) -> Image.Image:
    """Товар на прозрачном фоне (RGBA). Единственное место, где вызывается нейросеть."""
    global _session
    try:
        from rembg import new_session, remove
    except ImportError as exc:
        raise RembgUnavailable(str(exc)) from exc
    if _session is None:
        _session = new_session(MODEL)
    return remove(img, session=_session, post_process_mask=True)


def render(img: Image.Image) -> bytes | None:
    """Вырезать товар, положить на белый квадрат. None — нейросеть товар не нашла."""
    cutout = cut_out(img.convert("RGB")).convert("RGBA")
    bbox = cutout.getchannel("A").point(lambda v: 255 if v > ALPHA_CUT else 0).getbbox()
    if bbox is None:
        return None
    product = image_processing.flatten_on_white(cutout.crop(bbox))
    buf = io.BytesIO()
    image_processing.fit_into_square(product).save(
        buf, format="WEBP", quality=image_processing.QUALITY
    )
    return buf.getvalue()
