"""Read-only snapshot taxonomy state на staging (no-op seed verification)."""
import json

from apps.catalog.models import (
    Attribute,
    AttributeOption,
    CategoryAttribute,
    ProductAttributeValue,
)
from apps.catalog.taxonomy_manifest import load_manifest, taxonomy_identity_hash

a = Attribute.objects.get(slug="tool_type")
opts = sorted(
    (
        {"id": o.id, "slug": o.slug, "value": o.value, "sort_order": o.sort_order}
        for o in a.options.all()
    ),
    key=lambda x: x["slug"],
)
pav_count = ProductAttributeValue.objects.filter(attribute=a).count()
bindings = sorted(
    (
        {
            "category_id": ca.category_id,
            "attribute_id": ca.attribute_id,
            "is_required": ca.is_required,
            "is_filter": ca.is_filter,
            "group": ca.group,
            "is_seo_facet": ca.is_seo_facet,
        }
        for ca in CategoryAttribute.objects.filter(attribute=a)
    ),
    key=lambda x: x["category_id"],
)
m = load_manifest()
print(
    json.dumps(
        {
            "option_count": len(opts),
            "live_identity": taxonomy_identity_hash(opts),
            "manifest_identity": m.identity_hash,
            "manifest_semantic": m.semantic_hash,
            "pav_count": pav_count,
            "binding_count": len(bindings),
            "options": opts,
            "bindings": bindings,
        },
        ensure_ascii=False,
    )
)
