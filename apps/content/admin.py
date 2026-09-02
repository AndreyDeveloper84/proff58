from django.contrib import admin
from django.utils.html import format_html, format_html_join
from django.utils.safestring import mark_safe

from .article_markup import parse_body, parse_summary, reading_minutes
from .models import Article, Banner, Promotion, SEOPage

# Витрина эти модели не читает: у apps.content нет API, тексты главной и статьи
# заданы в коде фронтенда (frontend/lib/home-content.ts, frontend/lib/articles.ts).
# Пока это так, каждый список предупреждает об этом — иначе человек заполняет
# баннеры и ждёт их на сайте. Убрать вместе с подключением контента к витрине.
NOT_WIRED_TEMPLATE = "admin/content/not_wired_change_list.html"


@admin.register(SEOPage)
class SEOPageAdmin(admin.ModelAdmin):
    # Предупреждения «витрина это не читает» здесь больше нет: инфо-страницы
    # доходят до сайта (/info/<slug>), и правка в этой форме меняет страницу.
    list_display = ["slug", "title", "status", "updated_at"]
    list_filter = ["status"]
    search_fields = ["slug", "title"]
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = [
        (None, {"fields": ["slug", "title", "status", "body"]}),
        ("SEO", {"fields": ["meta_title", "meta_description"], "classes": ["collapse"]}),
    ]


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ["title", "tag", "status", "published_at", "created_at"]
    list_filter = ["status", "tag"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    autocomplete_fields = ["catalog_category"]
    readonly_fields = ["structure_preview"]
    fieldsets = [
        (None, {"fields": ["slug", "title", "status", "published_at"]}),
        (
            "Как выглядит статья",
            {
                "fields": ["tag", "cover", "figure", "catalog_category", "reading_minutes"],
                "description": (
                    "Схема-иллюстрация открывает статью вместо фото и объясняет тему "
                    "чертежом. «Раздел каталога» включает под статьёй блок с товарами."
                ),
            },
        ),
        (
            "Текст",
            {
                "fields": ["excerpt", "summary", "body", "structure_preview"],
                "description": (
                    "Разметка: <b>## </b> — заголовок раздела, <b>- </b> — пункт списка, "
                    "<b>&gt; </b> — врезка, строка из <b>|</b> — таблица (первая строка "
                    "= шапка). Всё остальное — обычные абзацы. Ниже видно, как текст "
                    "разобрался — проверьте перед публикацией."
                ),
            },
        ),
        ("SEO", {"fields": ["meta_title", "meta_description"], "classes": ["collapse"]}),
    ]

    @admin.display(description="Как разобрался текст")
    def structure_preview(self, obj):
        """Показывает результат разбора разметки.

        Без него человек пишет вслепую: опечатка в «##» молча превращает
        заголовок в абзац, и увидеть это можно только на сайте.
        """
        if obj is None or not obj.body:
            return mark_safe(  # noqa: S308
                '<span style="opacity:.6;">Наберите текст — здесь появится разбор.</span>'
            )

        sections = parse_body(obj.body)
        if not sections:
            return mark_safe('<span style="opacity:.6;">Пусто.</span>')  # noqa: S308

        rows = []
        for section in sections:
            heading = section["heading"] or "(вступление без заголовка)"
            kinds = ", ".join(
                {
                    "text": "абзац",
                    "list": "список",
                    "table": "таблица",
                    "note": "врезка",
                }.get(block["kind"], block["kind"])
                for block in section["blocks"]
            )
            rows.append((heading, kinds or "пусто"))

        return format_html(
            '<div style="max-width:44rem;">{}<div style="margin-top:.5rem;opacity:.6;'
            'font-size:.85em;">Время чтения: {} мин · пунктов «коротко»: {}</div></div>',
            format_html_join(
                "",
                '<div style="margin:.15rem 0;"><b>{}</b>'
                ' <span style="opacity:.65;">— {}</span></div>',
                rows,
            ),
            obj.reading_minutes or reading_minutes(obj.body),
            len(parse_summary(obj.summary)),
        )


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
    change_list_template = NOT_WIRED_TEMPLATE
    list_display = ["title", "status", "starts_at", "ends_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = [
        (None, {"fields": ["slug", "title", "status", "cover"]}),
        ("Период", {"fields": ["starts_at", "ends_at"]}),
        ("Описание", {"fields": ["description"]}),
    ]


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    change_list_template = NOT_WIRED_TEMPLATE
    list_display = ["title", "target", "sort_order", "status"]
    list_filter = ["status", "target"]
    search_fields = ["title"]
    fieldsets = [
        (None, {"fields": ["title", "image", "alt", "link", "target", "sort_order", "status"]}),
    ]
