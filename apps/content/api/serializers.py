"""Сериализаторы контента витрины: информационные страницы и статьи."""

from __future__ import annotations

from rest_framework import serializers

from ..article_markup import parse_body, parse_summary, reading_minutes
from ..models import Article, SEOPage
from ..page_markup import parse_page_body


class InfoPageListSerializer(serializers.ModelSerializer):
    """Пункт меню: только то, что нужно для ссылки в подвале."""

    class Meta:
        model = SEOPage
        fields = ("slug", "title")


class InfoPageSerializer(serializers.ModelSerializer):
    """Страница целиком: разметка уже разобрана в типизированные секции.

    Разбор делает сервер — как у статей: витрина получает готовую структуру и не
    тащит парсер, поэтому правило разметки одно на всю систему.

    ``body`` при этом остаётся в ответе. Во-первых, старые страницы написаны
    сплошным текстом и должны показываться абзацами, пока их не переписали. Во
    вторых, это обычный текст, а не HTML: страницу пишет человек в админке, и
    вставка её как разметки открыла бы XSS через контент-редактора.
    """

    updated_at = serializers.DateTimeField(read_only=True)
    sections = serializers.SerializerMethodField()

    class Meta:
        model = SEOPage
        fields = (
            "slug",
            "title",
            "body",
            "sections",
            "meta_title",
            "meta_description",
            "updated_at",
        )

    def get_sections(self, obj) -> list[dict]:
        return parse_page_body(obj.body)


class ArticleListSerializer(serializers.ModelSerializer):
    """Карточка статьи в ленте."""

    image = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    readingMinutes = serializers.SerializerMethodField()  # noqa: N815 — контракт витрины

    class Meta:
        model = Article
        fields = ("slug", "title", "excerpt", "tag", "figure", "image", "date", "readingMinutes")

    def get_image(self, obj) -> str:
        return obj.cover.url if obj.cover else ""

    def get_date(self, obj) -> str:
        moment = obj.published_at or obj.created_at
        return moment.date().isoformat() if moment else ""

    def get_readingMinutes(self, obj) -> int:  # noqa: N802 — контракт витрины
        return obj.reading_minutes or reading_minutes(obj.body)


class ArticleSerializer(ArticleListSerializer):
    """Статья целиком — разметка уже разобрана в секции с блоками.

    Разбор делает сервер: витрина получает готовую структуру и не тащит парсер,
    а значит правило разметки одно на всю систему.
    """

    summary = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()
    catalog = serializers.SerializerMethodField()

    class Meta(ArticleListSerializer.Meta):
        fields = (
            *ArticleListSerializer.Meta.fields,
            "summary",
            "sections",
            "catalog",
            "meta_title",
            "meta_description",
        )

    def get_summary(self, obj) -> list[str]:
        return parse_summary(obj.summary)

    def get_sections(self, obj) -> list[dict]:
        return parse_body(obj.body)

    def get_catalog(self, obj) -> dict | None:
        if obj.catalog_category_id is None:
            return None
        return {"slug": obj.catalog_category.slug, "label": obj.catalog_category.name}
