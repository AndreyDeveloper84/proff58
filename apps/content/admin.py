from django.contrib import admin

from .models import Article, Banner, Promotion, SEOPage


@admin.register(SEOPage)
class SEOPageAdmin(admin.ModelAdmin):
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
    list_display = ["title", "status", "published_at", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "slug"]
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = [
        (None, {"fields": ["slug", "title", "status", "cover", "published_at"]}),
        ("Содержимое", {"fields": ["excerpt", "body"]}),
        ("SEO", {"fields": ["meta_title", "meta_description"], "classes": ["collapse"]}),
    ]


@admin.register(Promotion)
class PromotionAdmin(admin.ModelAdmin):
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
    list_display = ["title", "target", "sort_order", "status"]
    list_filter = ["status", "target"]
    search_fields = ["title"]
    fieldsets = [
        (None, {"fields": ["title", "image", "alt", "link", "target", "sort_order", "status"]}),
    ]
