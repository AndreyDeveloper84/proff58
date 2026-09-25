# Проверка/установка display_name для CAT-03 (Windows-консоль портит кириллицу в -c).
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from apps.catalog.models import Category, CategoryAttribute  # noqa: E402

cat = Category.objects.get(slug="izmeritelnyy-ugolniki-i-lineyki")
ca = CategoryAttribute.objects.get(category=cat, attribute__slug="size")
target = "Размер"
if ca.display_name != target:
    ca.display_name = target
    ca.save(update_fields=["display_name"])
    print("fixed ->", repr(ca.display_name))
else:
    print("ok:", repr(ca.display_name))

# Контроль: у ключей подпись не задана (fallback на имя атрибута)
for row in CategoryAttribute.objects.filter(attribute__slug="size").exclude(pk=ca.pk):
    assert row.display_name == "", (row.category.slug, row.display_name)
print("other size rows clean:", CategoryAttribute.objects.filter(attribute__slug="size").count())
