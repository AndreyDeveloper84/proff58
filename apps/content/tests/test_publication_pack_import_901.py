"""Safety checks for the Publication Pack 01 draft importer."""

import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class PublicationPackImportSafetyTests(SimpleTestCase):
    def _archive(self, path: Path, *, slug: str, status: str) -> None:
        metadata = {
            "slug": slug,
            "status": status,
            "body_file": "article_body.cms.md",
            "cover": "media/perforator-guide-cover.png",
        }
        with ZipFile(path, "w") as package:
            package.writestr("publication_pack_01/article_metadata.json", json.dumps(metadata))
            package.writestr("publication_pack_01/article_body.cms.md", "## Раздел\\nТекст")
            package.writestr("publication_pack_01/media/perforator-guide-cover.png", b"image")

    def test_rejects_published_status_before_database_access(self):
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "pack.zip"
            self._archive(archive, slug="kak-vybrat-perforator", status="published")
            with self.assertRaisesMessage(CommandError, "non-draft"):
                call_command(
                    "import_publication_pack_01",
                    archive,
                    category_slug="perforatory",
                    stdout=StringIO(),
                )

    def test_rejects_unexpected_slug_before_database_access(self):
        with TemporaryDirectory() as directory:
            archive = Path(directory) / "pack.zip"
            self._archive(archive, slug="other-article", status="draft")
            with self.assertRaisesMessage(CommandError, "Unexpected slug"):
                call_command(
                    "import_publication_pack_01",
                    archive,
                    category_slug="perforatory",
                    stdout=StringIO(),
                )
