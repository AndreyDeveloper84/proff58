# E2E через реальный facets-view (APIClient, локальная БД): угольники vs ключи.
import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from rest_framework.test import APIClient  # noqa: E402

c = APIClient()
for slug in ("izmeritelnyy-ugolniki-i-lineyki", "ruchnoy-klyuchi"):
    resp = c.get(f"/api/catalog/categories/{slug}/facets/")
    assert resp.status_code == 200, (slug, resp.status_code)
    facet = next((f for f in resp.json()["facets"] if f["slug"] == "size"), None)
    print(slug, "->", None if facet is None else (facet["slug"], facet["name"], facet["unit"]))
