"""Стартовый экран админки «Сегодня».

Зачем: по умолчанию вход в админку — список из шестнадцати разделов, который не
отвечает на вопрос «что мне сейчас делать». Здесь вместо этого — очереди работы
со счётчиками, каждая ведёт в уже отфильтрованный список.

Почему в `config/`, а не в `apps/core/`: карточки читают каталог, заказы, заявки
и отзывы, а ядро по правилу зависимостей (CLAUDE.md §4) не зависит ни от кого.
`config` — слой сборки проекта, ему знать обо всех приложениях можно.

Числа берутся из `apps.catalog.queues` — того же кода, что стоит за фильтрами
списка товаров, чтобы счётчик и открытая по ссылке страница не расходились.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig
from django.http import HttpResponseRedirect

# Куда ведёт название раздела (хлебная крошка «Заказы», «Каталог»…), если в
# разделе несколько моделей. Без записи берётся первая видимая в меню модель —
# для catalog это была бы «Автораскладка», для payments — «Возвраты».
APP_HOME = {
    "orders": "order",
    "catalog": "product",
    "payments": "payment",
    "content": "article",
    "delivery": "deliveryzone",
}


def _card(label, count, url, *, tone="info", hint=""):
    return {"label": label, "count": count, "url": url, "tone": tone, "hint": hint}


def _orders_group():
    from apps.orders.models import FulfillmentStatus, Order, PaymentStatus, Sync1CStatus

    base = "/admin/orders/order/"
    return {
        "title": "Заказы",
        "cards": [
            _card(
                "Новые — подтвердить",
                Order.objects.filter(fulfillment_status=FulfillmentStatus.NEW).count(),
                f"{base}?fulfillment_status__exact={FulfillmentStatus.NEW}",
                tone="danger",
                hint="Покупатель ждёт подтверждения",
            ),
            _card(
                "Ждут оплаты",
                Order.objects.filter(payment_status=PaymentStatus.PENDING).count(),
                f"{base}?payment_status__exact={PaymentStatus.PENDING}",
                tone="warning",
            ),
            _card(
                "Не ушли в 1С",
                Order.objects.filter(sync_1c_status=Sync1CStatus.PENDING).count(),
                f"{base}?sync_1c_status__exact={Sync1CStatus.PENDING}",
                tone="warning",
                hint="1С ещё не забрала заказ",
            ),
        ],
    }


def _catalog_group():
    from apps.catalog import queues

    base = "/admin/catalog/product/"
    return {
        "title": "Товары",
        "cards": [
            _card(
                "Разобрать каталог",
                queues.needs_attention().count(),
                "/admin/catalog/product/moderate/",
                tone="danger",
                hint="Открыть конвейер: один товар — заполнить — опубликовать",
            ),
            _card(
                "Без категории",
                queues.without_category().count(),
                f"{base}?categorized=no",
                tone="warning",
            ),
            _card("Без фото", queues.without_image().count(), f"{base}?content=no_image"),
            _card(
                "Без описания",
                queues.without_description().count(),
                f"{base}?content=no_description",
            ),
        ],
    }


def _requests_group():
    from apps.leads.models import InquiryStatus, ProductInquiry
    from apps.reviews.models import Review, ReviewStatus
    from apps.sync_1c.models import SyncLog

    return {
        "title": "Обращения и обмен",
        "cards": [
            _card(
                "Новые заявки",
                ProductInquiry.objects.filter(status=InquiryStatus.NEW).count(),
                f"/admin/leads/productinquiry/?status__exact={InquiryStatus.NEW}",
                tone="danger",
                hint="Человек оставил телефон и ждёт звонка",
            ),
            _card(
                "Отзывы на модерации",
                Review.objects.filter(status=ReviewStatus.PENDING).count(),
                f"/admin/reviews/review/?status__exact={ReviewStatus.PENDING}",
                tone="warning",
            ),
            _card(
                "Ошибки обмена с 1С",
                SyncLog.objects.filter(result=SyncLog.SyncResult.ERROR).count(),
                f"/admin/sync_1c/synclog/?result__exact={SyncLog.SyncResult.ERROR}",
                tone="warning",
                hint="Цены и остатки могли не обновиться",
            ),
        ],
    }


def build_today_groups():
    """Очереди для стартового экрана. Пустые карточки не показываем — незачем
    занимать внимание нулями; группа целиком без работы тоже скрывается."""
    groups = []
    for builder in (_orders_group, _catalog_group, _requests_group):
        group = builder()
        group["cards"] = [c for c in group["cards"] if c["count"]]
        if group["cards"]:
            groups.append(group)
    return groups


class ProffAdminSite(AdminSite):
    """Админка «Профессионала» с рабочим стартовым экраном."""

    index_template = "admin/dashboard.html"

    def index(self, request, extra_context=None):
        context = dict(extra_context or {})
        context["today_groups"] = build_today_groups()
        return super().index(request, extra_context=context)

    def app_index(self, request, app_label, extra_context=None):
        """Название раздела ведёт в его главный список, а не на страницу раздела.

        Штатная страница `/admin/<app>/` в jazzmin — английский заголовок
        («Orders»), модели вперемешку с полками и подсвеченная «Админпанель»:
        человек жал «Заказы» в хлебных крошках и попадал «куда-то не туда».

        Редирект временный (302): цель зависит от прав пользователя, 301 браузер
        закешировал бы. Нет раздела или прав — штатное поведение Django (404).
        """
        url = self._app_home_url(request, app_label)
        if url is None:
            return super().app_index(request, app_label, extra_context)
        return HttpResponseRedirect(url)

    def _app_home_url(self, request, app_label):
        # get_app_list уже отфильтрован по правам; admin_url есть только у моделей,
        # список которых пользователю разрешено открыть.
        models = [
            m
            for app in self.get_app_list(request, app_label)
            for m in app["models"]
            if m.get("admin_url")
        ]
        if not models:
            return None
        hidden = {x.lower() for x in settings.JAZZMIN_SETTINGS.get("hide_models", [])}

        def key(m):
            return m["object_name"].lower()

        home = APP_HOME.get(app_label)
        visible = [m for m in models if f"{app_label}.{key(m)}" not in hidden]
        chosen = next((m for m in models if key(m) == home), None) or (visible or models)[0]
        return chosen["admin_url"]


class ProffAdminConfig(AdminConfig):
    """Подменяет admin.site на ProffAdminSite (INSTALLED_APPS)."""

    default_site = "config.admin_site.ProffAdminSite"
