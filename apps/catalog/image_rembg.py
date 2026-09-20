"""Удаление фона нейросетью rembg (ADR-0014, итерация 2).

Только для фото на чёрном фоне: прочий фон автообработка не трогает вовсе
(`image_autoprocess`). Работает только в образе сервиса `celery-rembg`
(`requirements/images.txt`): rembg тянет onnxruntime, scipy, scikit-image, numba
и opencv, поэтому в остальные образы не ставится. Без него `is_available()` —
False, и фото спокойно ждут сервис.

Цена на 2 ядрах стенда: 4–5 с на фото, пик памяти ~2,1 ГБ (прогон 113 фото
20.09.2026; первое фото дольше — качается модель). Модель одна на процесс.

Чёрный фон нейросеть снимает чисто: 65 копий из 67 на стенде — провода, шнуры
и текст на корпусе целы. Оставшиеся две — рекламные карточки бренда с текстом
на чёрном фоне: буквы ушли в фон, остались обрывки. Такую рвань ловит
`Square.torn` и отдаёт менеджеру вместо витрины.
"""

from __future__ import annotations

import importlib.util

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


def render(img: Image.Image) -> image_processing.Square | None:
    """Вырезать товар, положить на белый квадрат. None — нейросеть товар не нашла."""
    cutout = cut_out(img.convert("RGB")).convert("RGBA")
    bbox = cutout.getchannel("A").point(lambda v: 255 if v > ALPHA_CUT else 0).getbbox()
    if bbox is None:
        return None
    product = image_processing.flatten_on_white(cutout.crop(bbox))
    return image_processing.to_square(product, measure_pieces=True)
