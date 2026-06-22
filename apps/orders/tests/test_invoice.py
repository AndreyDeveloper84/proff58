"""Тесты B2B реквизитов и выставления счёта (#53)."""

from decimal import Decimal

import pytest

from apps.orders.invoice import prepare_b2b_order, prepare_invoice, validate_b2b_requisites


class TestValidateB2BRequisites:
    def test_valid_inn_10(self):
        assert validate_b2b_requisites("7701234567", "ООО Тест") == []

    def test_valid_inn_12(self):
        assert validate_b2b_requisites("770123456789", "ИП Иванов") == []

    def test_empty_inn(self):
        errors = validate_b2b_requisites("", "ООО Тест")
        assert any("ИНН" in e for e in errors)

    def test_letters_in_inn(self):
        errors = validate_b2b_requisites("770ABC4567", "ООО Тест")
        assert any("цифр" in e for e in errors)

    def test_inn_wrong_length_9(self):
        errors = validate_b2b_requisites("123456789", "ООО Тест")
        assert any("10 или 12" in e for e in errors)

    def test_inn_wrong_length_11(self):
        errors = validate_b2b_requisites("12345678901", "ООО Тест")
        assert any("10 или 12" in e for e in errors)

    def test_empty_company_name(self):
        errors = validate_b2b_requisites("7701234567", "")
        assert any("Название" in e for e in errors)

    def test_whitespace_company_name(self):
        errors = validate_b2b_requisites("7701234567", "   ")
        assert any("Название" in e for e in errors)

    def test_both_invalid(self):
        errors = validate_b2b_requisites("", "")
        assert len(errors) == 2


@pytest.mark.django_db
class TestPrepareInvoice:
    @pytest.fixture
    def b2b_order(self):
        from django.contrib.auth import get_user_model

        from apps.accounts.models import CustomerType, Profile
        from apps.catalog.models import Product, ProductStatus
        from apps.orders.models import Cart
        from apps.orders.services import place_order

        User = get_user_model()
        user = User.objects.create_user(
            phone="+79001111111",
            password="pass",
            customer_type=CustomerType.B2B,
            full_name="Директор",
        )
        Profile.objects.create(
            user=user,
            company_name='ООО "Строй"',
            inn="7701234567",
            kpp="770101001",
            legal_address="г. Пенза, ул. Мира, 1",
        )
        product = Product.objects.create(
            name="Дрель",
            slug="drel-b2b",
            price=Decimal("5000.00"),
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_quantity=10,
            available_quantity=10,
        )
        cart = Cart.objects.create(user=user)
        from apps.orders.models import CartItem

        CartItem.objects.create(cart=cart, product=product, quantity=2)
        order = place_order(cart, user=user)
        return order

    def test_b2b_order_has_requisites(self, b2b_order):
        assert b2b_order.inn == "7701234567"
        assert b2b_order.company_name == 'ООО "Строй"'

    def test_prepare_invoice_returns_data(self, b2b_order):
        data = prepare_invoice(b2b_order)
        assert data.order_number == b2b_order.order_number
        assert data.total == b2b_order.total
        assert data.buyer["inn"] == "7701234567"
        assert len(data.items) == 1
        assert data.items[0].quantity == 2

    def test_prepare_b2b_order_ok(self, b2b_order):
        data = prepare_b2b_order(b2b_order)
        assert data.order_number == b2b_order.order_number

    def test_prepare_b2b_rejects_b2c(self, b2b_order):
        b2b_order.customer_type = "b2c"
        with pytest.raises(ValueError, match="B2B"):
            prepare_b2b_order(b2b_order)


@pytest.mark.django_db
class TestB2COrderNoRequisites:
    def test_b2c_no_company(self):
        from django.contrib.auth import get_user_model

        from apps.catalog.models import Product, ProductStatus
        from apps.orders.models import Cart, CartItem
        from apps.orders.services import place_order

        User = get_user_model()
        user = User.objects.create_user(phone="+79002222222", password="pass")
        product = Product.objects.create(
            name="Пила",
            slug="pila-b2c",
            price=Decimal("3000.00"),
            status=ProductStatus.PUBLISHED,
            is_active=True,
            stock_quantity=5,
            available_quantity=5,
        )
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=1)
        order = place_order(cart, user=user)
        assert order.inn == ""
        assert order.company_name == ""
