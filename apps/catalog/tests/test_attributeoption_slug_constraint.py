"""DB-инвариант DEVIATION-2: (attribute, slug) уникален для непустых slug."""

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import Attribute, AttributeOption, AttributeType


@pytest.mark.django_db
def test_duplicate_nonempty_slug_rejected():
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="A", slug="dup")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            AttributeOption.objects.create(attribute=attr, value="B", slug="dup")


@pytest.mark.django_db
def test_same_slug_allowed_across_different_attributes():
    a1 = Attribute.objects.create(slug="tool_type", name="T", attribute_type=AttributeType.SELECT)
    a2 = Attribute.objects.create(slug="material", name="M", attribute_type=AttributeType.SELECT)
    AttributeOption.objects.create(attribute=a1, value="A", slug="same")
    AttributeOption.objects.create(attribute=a2, value="B", slug="same")  # не падает


@pytest.mark.django_db
def test_blank_slug_still_allowed_multiple():
    attr = Attribute.objects.create(
        slug="tool_type", name="Тип инструмента", attribute_type=AttributeType.SELECT
    )
    AttributeOption.objects.create(attribute=attr, value="A", slug="")
    AttributeOption.objects.create(attribute=attr, value="B", slug="")  # не падает
