# Publication Pack 01 — staging draft acceptance (#901)

Source: owner-provided `publication_pack_01_v2_expanded(1).zip`. Do **not** commit the ZIP, media, or article to GitHub. This runbook does not authorize a production publish or PR merge.

## Preconditions

1. Deploy the importer code to an isolated staging environment (the PR branch is **not** deployed automatically merely because PR CI passes).
2. Transfer the original ZIP securely to staging (e.g. `/tmp/publication_pack_01.zip`); verify its checksum against the local original. Never substitute a reconstructed package.
3. Use staging Django settings and database only. Check the environment/database target before running commands.
4. Determine the **existing** active, relevant catalog category slug from the staging database; do not assume `perforatory` exists:

   ```bash
   python manage.py shell -c "from apps.catalog.models import Category; print(list(Category.objects.filter(name__icontains='перфоратор', is_active=True).values('id','name','slug','on_site','is_site_v2')))"
   ```

   Confirm the category is the correct site-facing catalog category, not a legacy 1C node.

## Validate (read-only)

```bash
python manage.py import_publication_pack_01 /tmp/publication_pack_01.zip --category-slug ACTUAL_VERIFIED_SLUG
```

The command must report `Validated ... no database or storage changes`. If the slug already exists, the importer intentionally refuses to overwrite it unless the explicit `--update-existing-draft` option is used. Do not use that option without reviewing the existing draft.

## Import draft (staging only)

```bash
python manage.py import_publication_pack_01 /tmp/publication_pack_01.zip --category-slug ACTUAL_VERIFIED_SLUG --apply
```

Verify without modifying publication state:

```bash
python manage.py shell -c "from apps.content.models import Article; a=Article.objects.get(slug='kak-vybrat-perforator'); print({'id':a.pk,'status':a.status,'published_at':a.published_at,'category_id':a.catalog_category_id,'cover':a.cover.name,'body_chars':len(a.body)})"
```

Expected: `status='draft'`, `published_at=None`, nonempty body and cover, correct category.

## Acceptance evidence

- Unauthenticated `GET /api/content/articles/kak-vybrat-perforator/` should return **404** for the draft; public `/articles/kak-vybrat-perforator` should not show the draft.
- Review content and cover in authenticated Django Admin. A public URL for a draft is **not** a preview; authenticated preview requires an explicit protected implementation.
- Verify rendered SEO, canonical, Markdown links, cover, tables, lists and mobile overflow on a **separately authorized staging preview** or after a specifically authorized staging-only publication. Do not mark these gates passed based solely on API tests.
- Record environment, commit SHA, category ID/slug, commands, redacted logs, screenshots, URLs and reviewer decision in PR #902.
- External originality report remains a manual gate. Do not invent an originality score.

## Release restrictions

Never run `--apply` against production. Do not set `published`, merge PR #902, or deploy production without separate owner approval.
