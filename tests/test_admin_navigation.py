"""Навигация админки: куда на самом деле ведут ссылки.

Поводом была жалоба «жму "Заказы" — попадаю не в заказы»: название раздела в
хлебных крошках вело на служебную страницу `/admin/orders/` с английским
заголовком и полками вперемешку с моделями. Здесь закреплено, что название
раздела ведёт в его главный список, а готовые ссылки меню и стартового экрана
открывают то, что обещают.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from apps.orders.models import Order
from config import admin_site
from config.admin_site import APP_HOME

User = get_user_model()

APP_LABELS = sorted({m._meta.app_label for m in admin.site._registry})


@pytest.fixture
def админ(db, client):
    user = User.objects.create_superuser(phone="+79990000001", password="pwd12345")
    client.force_login(user)
    return client


def _staff_с_правами(client, *codenames):
    user = User.objects.create_user(phone="+79990000002", password="pwd12345", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    client.force_login(user)
    return client


@pytest.mark.parametrize("app_label", APP_LABELS)
def test_название_раздела_ведёт_в_рабочий_список(админ, app_label):
    """В т.ч. разделы, где всё скрыто из меню (ai, analytics, auth)."""
    response = админ.get(reverse("admin:app_list", args=[app_label]))

    # 302, не 301: цель зависит от прав, постоянный редирект браузер закеширует.
    assert response.status_code == 302
    assert response["Location"].startswith(f"/admin/{app_label}/")
    assert админ.get(response["Location"]).status_code == 200


@pytest.mark.parametrize(
    ("app_label", "ожидаемый"),
    [("orders", "/admin/orders/order/"), ("catalog", "/admin/catalog/product/")],
)
def test_заказы_ведут_в_заказы_а_каталог_в_товары(админ, app_label, ожидаемый):
    response = админ.get(f"/admin/{app_label}/")
    assert response["Location"] == ожидаемый


def test_карта_главных_списков_указывает_на_зарегистрированные_модели():
    """Переименование модели не должно молча сломать карту."""
    registered = {(m._meta.app_label, m._meta.model_name) for m in admin.site._registry}
    assert set(APP_HOME.items()) <= registered


def test_главный_список_выбирается_с_учётом_прав(db, client):
    """Видит только счета B2B — «Заказы» ведут в счета, а не в 403 на заказах."""
    client = _staff_с_правами(client, "view_b2binvoice")
    response = client.get("/admin/orders/")
    assert response.status_code == 302
    assert response["Location"] == "/admin/orders/b2binvoice/"


def test_только_право_добавлять_не_даёт_ошибки(db, client):
    """У модели без права просмотра нет списка — остаётся штатная страница раздела."""
    client = _staff_с_правами(client, "add_order")
    assert client.get("/admin/orders/").status_code == 200


def test_раздел_без_прав_и_несуществующий_раздел_дают_404(db, client):
    client = _staff_с_правами(client, "view_b2binvoice")
    assert client.get("/admin/catalog/").status_code == 404
    assert client.get("/admin/net-takogo/").status_code == 404


def test_аноним_уходит_на_вход(db, client):
    response = client.get("/admin/orders/")
    assert response.status_code == 302
    assert response["Location"].startswith("/admin/login/")


def _готовые_ссылки():
    jazzmin = settings.JAZZMIN_SETTINGS
    links = [*jazzmin["topmenu_links"]]
    for shelf in jazzmin["custom_links"].values():
        links.extend(shelf)
    urls = {link["url"] for link in links if link["url"].startswith("/admin/")}
    # Карточки берём из билдеров напрямую: build_today_groups прячет нулевые,
    # и на пустой базе проверять было бы нечего.
    for builder in (
        admin_site._orders_group,
        admin_site._catalog_group,
        admin_site._requests_group,
    ):
        urls.update(card["url"] for card in builder()["cards"])
    return sorted(urls)


def test_готовые_ссылки_меню_и_карточек_открываются(админ):
    """Битый фильтр Django не роняет, а молча уводит на `?e=1` — поэтому без follow."""
    for url in _готовые_ссылки():
        assert админ.get(url).status_code == 200, url


def test_быстрые_действия_стартового_экрана_открываются(админ):
    html = админ.get("/admin/").content.decode()
    quick = re.search(r'<p class="today-quick">(.*?)</p>', html, re.S).group(1)
    urls = re.findall(r'href="([^"]+)"', quick)
    assert len(urls) == 5
    for url in urls:
        assert админ.get(url).status_code == 200, url


def test_в_списке_разделов_стартового_экрана_нет_полок(админ):
    """Полка — готовая выборка, а не модель: строка «Новые — Изменить» сбивала с толку."""
    html = админ.get("/admin/").content.decode()
    block = html[html.index('id="dashboard-apps"') : html.index('id="content-related"')]

    assert "/admin/orders/order/" in block
    assert "/admin/catalog/product/" in block
    assert "?fulfillment_status__exact=new" not in block
    assert "/moderate/" not in block
    # скрытые из меню модели по-прежнему скрыты
    assert "/admin/orders/cart/" not in block


def test_столбцы_дат_подписаны_по_русски(админ):
    # Без строк таблица с заголовками не рисуется — нужен хотя бы один заказ.
    Order.objects.create(order_number="T-NAV-1", total=Decimal("100.00"))

    html = админ.get("/admin/orders/order/").content.decode()
    assert "column-created" in html
    assert "Создано" in html
    assert "Created at" not in html
