"""Главное фото товара для чужих модулей — корзины, заказов, кабинета.

Карточка каталога берёт фото из собственного сериализатора, где картинки уже
подгружены вместе с товаром. Корзине и заказу так не повезло: у них на руках
только ``product_id``, а читать таблицы каталога из ``orders`` запрещает граница
модулей (ADR-0004). Отсюда отдельная функция: один запрос на все товары сразу,
тот же выбор главного фото, что и в выдаче каталога, тот же относительный адрес.
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import ProductImage


def main_image_urls(product_ids: Iterable[int | None]) -> dict[int, str]:
    """``product_id → адрес главного фото`` для товаров, у которых фото есть.

    Главное — помеченное ``is_main``, иначе первое по порядку: ровно так же
    выбирает карточка каталога, иначе в корзине и в выдаче стояли бы разные кадры.
    Товары без фото в ответ не попадают — вызывающий показывает «Фото готовится».

    Адрес относительный (``/media/…``): витрина и медиа отдаются одним nginx, а
    абсолютный адрес с внутренним хостом ломает серверный рендер (см.
    ``catalog/api/serializers.py::_image_url``).
    """
    ids = {pid for pid in product_ids if pid}
    if not ids:
        return {}

    urls: dict[int, str] = {}
    images = ProductImage.objects.filter(product_id__in=ids).order_by(
        "product_id", "-is_main", "sort_order", "id"
    )
    for image in images:
        if image.product_id in urls:
            continue
        try:
            urls[image.product_id] = image.storefront_image.url
        except ValueError:
            # Запись без файла: берём следующее фото товара, если оно есть.
            continue
    return urls
