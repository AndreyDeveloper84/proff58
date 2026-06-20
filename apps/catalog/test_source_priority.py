"""Тесты приоритета источников значений характеристик (#96)."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.catalog.source_priority import Source, can_overwrite, rank


class SourcePriorityTests(SimpleTestCase):
    def test_rank_order(self):
        self.assertGreater(rank(Source.MANUAL), rank(Source.IMPORT_1C))
        self.assertGreater(rank(Source.IMPORT_1C), rank(Source.NAME_REGEX))
        self.assertGreater(rank(Source.NAME_REGEX), rank(Source.NAME_KEYWORD))
        self.assertGreater(rank(Source.NAME_KEYWORD), rank(Source.LLM))

    def test_rank_unknown_is_zero(self):
        self.assertEqual(rank(None), 0)
        self.assertEqual(rank(""), 0)
        self.assertEqual(rank("что-то"), 0)

    def test_empty_existing_can_be_written(self):
        self.assertTrue(can_overwrite(None, Source.LLM))
        self.assertTrue(can_overwrite("", Source.NAME_REGEX))

    def test_manual_not_overwritten_by_auto(self):
        self.assertFalse(can_overwrite(Source.MANUAL, Source.NAME_REGEX))
        self.assertFalse(can_overwrite(Source.MANUAL, Source.NAME_KEYWORD))
        self.assertFalse(can_overwrite(Source.MANUAL, Source.LLM))

    def test_import_1c_not_overwritten_by_auto(self):
        self.assertFalse(can_overwrite(Source.IMPORT_1C, Source.NAME_REGEX))
        self.assertFalse(can_overwrite(Source.IMPORT_1C, Source.LLM))

    def test_higher_overwrites_lower(self):
        self.assertTrue(can_overwrite(Source.LLM, Source.NAME_KEYWORD))
        self.assertTrue(can_overwrite(Source.NAME_KEYWORD, Source.NAME_REGEX))
        self.assertTrue(can_overwrite(Source.NAME_REGEX, Source.MANUAL))

    def test_equal_rank_allowed_for_idempotent_rerun(self):
        # Повторный прогон того же источника обновляет значение.
        self.assertTrue(can_overwrite(Source.NAME_REGEX, Source.NAME_REGEX))
        self.assertTrue(can_overwrite(Source.NAME_KEYWORD, Source.NAME_KEYWORD))
