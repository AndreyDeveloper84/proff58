# Result contract v1

## File location

```text
var/catalog-processing/inbox/<run_id>.result.json
```

## Top-level fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Must be `"1.0"`. |
| `run_id` | string | UUID of the `CatalogProcessingRun`. |
| `taxonomy_hash` | string | SHA-256 hex from the export file. |
| `export_checksum` | string | Value copied from the export file's `checksum` field. |
| `items` | array | One entry per researched product. |

## Item fields

| Field | Type | Description |
|---|---|---|
| `product_ref` | integer | Product ID, matches export. |
| `input_hash` | string | SHA-256 hex from export item. |
| `identity` | object | See below. |
| `status` | string | `researched`, `review`, `unknown`, or `identity_failed`. |
| `reason_code` | string | Short machine-readable reason. |
| `reason_detail` | string | Human-readable explanation. |
| `changes` | array | Changes proposed for this item (may be empty). |

### Identity object

| Field | Type | Description |
|---|---|---|
| `status` | string | `matched`, `partial`, `unknown`, or `mismatch`. |
| `brand` | string | Optional. |
| `model` | string | Optional. |
| `article` | string | Optional. |
| `reason` | string | Optional human explanation. |

## Change fields

| Field | Type | Description |
|---|---|---|
| `target_kind` | string | `"tool_type"` in v1. |
| `proposed_value` | object | `{"option_slug": "..."}`. |
| `confidence` | integer | `0..100`. |
| `source` | string | `"web"` or `"llm"`. |
| `reason_code` | string | Short reason. |
| `reason_detail` | string | Human explanation. |
| `evidence` | array | At least one evidence item for `web`/`llm`. |

## Evidence fields

| Field | Type | Description |
|---|---|---|
| `source_type` | string | `manufacturer`, `manufacturer_pdf`, `distributor`, `specialized_store`, `marketplace`. |
| `url` | string | Absolute HTTPS URL. |
| `title` | string | Page title. |
| `observed_value` | string | Exact text observed on the page. |
| `retrieved_at` | string | ISO-8601 timestamp. |

## Example

```json
{
  "schema_version": "1.0",
  "run_id": "f7a5d94d-d1f9-44f4-9a2e-8c5a4bf49ea1",
  "taxonomy_hash": "ea3105025045e344131bca33e88c565546c2d7abd1590af82b80d9fe7ddcfd0c",
  "export_checksum": "d927d3587b829dfe77aca6aa3b1de3fd3e5bdef21ddc85923dd7535fe53bfb96",
  "items": [
    {
      "product_ref": 1,
      "input_hash": "937ab170cf10bcc28f99c6f43d2814031d93270e4be38ac159384a7a25f47b20",
      "identity": {
        "status": "matched",
        "brand": "Smoke",
        "model": "Test 1C",
        "article": "SMOKE-1C-001",
        "reason": "exact article match"
      },
      "status": "researched",
      "reason_code": "exact_article_match",
      "reason_detail": "Артикул SMOKE-1C-001 точно совпадает с manufacturer catalog.",
      "changes": [
        {
          "target_kind": "tool_type",
          "proposed_value": {"option_slug": "drel"},
          "confidence": 95,
          "reason_code": "exact_model_match",
          "reason_detail": "Manufacturer page lists model as drill.",
          "source": "web",
          "evidence": [
            {
              "source_type": "manufacturer",
              "url": "https://example.com/products/smoke-test-1c",
              "title": "Smoke Test 1C Specification",
              "observed_value": "Дрель",
              "retrieved_at": "2026-07-18T10:00:00Z"
            }
          ]
        }
      ]
    }
  ]
}
```
