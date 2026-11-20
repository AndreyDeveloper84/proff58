"""Import Publication Pack 01 as a CMS draft; never publish automatically."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.catalog.models import Category
from apps.content.models import Article, PublishStatus

ROOT = "publication_pack_01/"
EXPECTED_SLUG = "kak-vybrat-perforator"


class Command(BaseCommand):
    help = "Import Publication Pack 01 into Article as draft (explicit category required)."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--category-slug", required=True)
        parser.add_argument("--apply", action="store_true", help="Write draft; default is validation only.")
        parser.add_argument(
            "--update-existing-draft",
            action="store_true",
            help="Allow updating only the existing draft with the same slug.",
        )

    def handle(self, *args, **options):
        archive = options["archive"]
        try:
            with ZipFile(archive) as package:
                names = set(package.namelist())
                metadata_path = ROOT + "article_metadata.json"
                if metadata_path not in names:
                    raise CommandError("Missing article_metadata.json")
                metadata = json.loads(package.read(metadata_path))
                if metadata.get("slug") != EXPECTED_SLUG or metadata.get("status") != "draft":
                    raise CommandError("Unexpected slug or non-draft publication status")
                body_path = ROOT + metadata.get("body_file", "")
                cover_path = ROOT + metadata.get("cover", "")
                if body_path not in names or cover_path not in names:
                    raise CommandError("Missing body or cover in archive")
                body = package.read(body_path).decode("utf-8")
                cover_bytes = package.read(cover_path)
        except (OSError, ValueError, KeyError) as exc:
            raise CommandError(f"Invalid publication archive: {exc}") from exc

        if not body.strip() or not cover_bytes:
            raise CommandError("Empty body or cover")
        categories = Category.objects.filter(slug=options["category_slug"], is_active=True)
        if categories.count() != 1:
            raise CommandError("Category slug must resolve to one active category")
        category = categories.get()
        existing = Article.objects.filter(slug=EXPECTED_SLUG).first()
        if existing and (
            existing.status != PublishStatus.DRAFT or not options["update_existing_draft"]
        ):
            raise CommandError("Existing article protected; update requires explicit draft opt-in")
        if not options["apply"]:
            self.stdout.write(
                f"Validated {EXPECTED_SLUG}; category={category.slug}; "
                "no database or storage changes (pass --apply to import)"
            )
            return

        fields = {
            key: metadata.get(key, "")
            for key in (
                "title",
                "meta_title",
                "meta_description",
                "excerpt",
                "summary",
                "tag",
                "figure",
                "reading_minutes",
            )
        }
        fields.update(
            body=body,
            catalog_category=category,
            status=PublishStatus.DRAFT,
            published_at=None,
        )
        with transaction.atomic():
            article = existing or Article(slug=EXPECTED_SLUG)
            for key, value in fields.items():
                setattr(article, key, value)
            article.full_clean(exclude=["cover"])
            article.save()
            article.cover.save("perforator-guide-cover.png", ContentFile(cover_bytes), save=True)
        self.stdout.write(self.style.SUCCESS(f"Draft saved: {article.slug} (id={article.pk})"))
