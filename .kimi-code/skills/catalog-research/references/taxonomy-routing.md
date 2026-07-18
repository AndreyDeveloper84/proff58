# Taxonomy routing for catalog research

## Tool type attribute

- Attribute slug: `tool_type`
- Value type: single-select (`AttributeOption`)
- The option is referenced by slug, never by display value.

## Allowed options

The export file lists all allowed options under `allowed_options`:

```json
{
  "allowed_options": [
    {"slug": "drel", "value": "Дрель"},
    {"slug": "dreli-shurupoverty", "value": "Дрели и шуруповёрты"}
  ]
}
```

The skill MUST:

- use only slugs from this list;
- return the slug in `proposed_value.option_slug`;
- never create, rename, or reinterpret options.

## Category hint

Each export item contains `category_path` and `category_id`. Use the path as a
hint, but the final decision must be an allowed option slug.

## Unknown or ambiguous cases

- If no allowed option clearly matches the researched product, return
  `status: "unknown"`.
- If product identity is matched but the target value is plausible rather than
  certain, return `status: "review"`; changes still require
  `identity.status: "matched"`.
- If identity could not be verified, return `status: "identity_failed"`.
