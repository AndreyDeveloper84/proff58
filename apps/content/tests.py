"""Тесты content app: публикация и видимость (#71)."""

from __future__ import annotations

import pytest

from .models import Article, Banner, BannerTarget, Promotion, PublishStatus, SEOPage


@pytest.fixture
def seo_page(db):
    return SEOPage.objects.create(slug="about", title="О компании", status=PublishStatus.PUBLISHED)


@pytest.fixture
def draft_page(db):
    return SEOPage.objects.create(slug="draft-page", title="Черновик", status=PublishStatus.DRAFT)


@pytest.fixture
def article(db):
    return Article.objects.create(slug="news-1", title="Новость", status=PublishStatus.PUBLISHED)


@pytest.fixture
def promotion(db):
    return Promotion.objects.create(slug="sale", title="Скидки", status=PublishStatus.PUBLISHED)


@pytest.fixture
def banner(db):
    return Banner.objects.create(
        title="Главный баннер",
        image="banners/test.jpg",
        target=BannerTarget.HOME,
        status=PublishStatus.PUBLISHED,
    )


# ── SEOPage ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_seo_page_is_published(seo_page):
    assert seo_page.is_published is True


@pytest.mark.django_db
def test_draft_page_not_published(draft_page):
    assert draft_page.is_published is False


@pytest.mark.django_db
def test_seo_page_str(seo_page):
    assert str(seo_page) == "О компании"


@pytest.mark.django_db
def test_published_pages_queryable(seo_page, draft_page):
    published = SEOPage.objects.filter(status=PublishStatus.PUBLISHED)
    assert seo_page in published
    assert draft_page not in published


# ── Article ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_article_is_published(article):
    assert article.is_published is True


@pytest.mark.django_db
def test_draft_article_not_published(db):
    a = Article.objects.create(slug="draft-art", title="Черновик", status=PublishStatus.DRAFT)
    assert a.is_published is False


@pytest.mark.django_db
def test_article_str(article):
    assert str(article) == "Новость"


# ── Promotion ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_promotion_is_published(promotion):
    assert promotion.is_published is True


@pytest.mark.django_db
def test_draft_promotion_not_published(db):
    p = Promotion.objects.create(slug="draft-promo", title="Черновик", status=PublishStatus.DRAFT)
    assert p.is_published is False


@pytest.mark.django_db
def test_promotion_str(promotion):
    assert str(promotion) == "Скидки"


# ── Banner ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_banner_is_published(banner):
    assert banner.is_published is True


@pytest.mark.django_db
def test_banner_target_home(banner):
    assert banner.target == BannerTarget.HOME


@pytest.mark.django_db
def test_banner_str(banner):
    assert str(banner) == "Главный баннер"


@pytest.mark.django_db
def test_draft_banner_not_published(db):
    b = Banner.objects.create(title="Черновик", image="banners/x.jpg", status=PublishStatus.DRAFT)
    assert b.is_published is False


@pytest.mark.django_db
def test_banners_filter_by_target(banner, db):
    catalog_banner = Banner.objects.create(
        title="Каталог",
        image="banners/cat.jpg",
        target=BannerTarget.CATALOG,
        status=PublishStatus.PUBLISHED,
    )
    home_banners = Banner.objects.filter(target=BannerTarget.HOME, status=PublishStatus.PUBLISHED)
    assert banner in home_banners
    assert catalog_banner not in home_banners
