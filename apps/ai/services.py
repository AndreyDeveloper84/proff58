"""Публичный контракт AI-возможностей: ``recommend()``, ``assist()`` (capability-срез).

V1 ``recommend`` — это ДЕТЕРМИНИРОВАННЫЙ EAV-движок БЕЗ LLM: подбор «похожих по
характеристикам» товаров по денормализованному ``Product.attrs_cache`` (источник —
EAV, который заполняет каталог). Контракт зафиксирован сейчас, внутренность
заменяема: сегодня правила по характеристикам, завтра — гибрид с LLM поверх того
же отобранного набора (см. ``docs/ARCHITECTURE-AI.md`` §3–4, сценарий Б).

Направление зависимости: ``apps.ai → apps.catalog`` (каталог о нас не знает).

Наблюдаемость (``AiCallLog`` из ``docs/ARCHITECTURE-AI.md`` §6) намеренно НЕ
добавлена: в V1 нет ни внешних, ни LLM-вызовов — журналировать нечего. Журнал
появится вместе с первым LLM-провайдером за портом (там и возникнут стоимость,
латентность и деградации, ради которых журнал существует).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json as _json
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.catalog import provenance
from apps.catalog.enrichment import AiAttr, apply_ai_enrichment, get_enrichable_product
from apps.catalog.filters import visible_products

from .guardrails import EnrichResult, parse_enrich_output
from .models import (
    AiCallLog,
    ContentFinding,
    ExternalCall,
    FindingApplicationAttempt,
    FindingEvidence,
    SourcingBudget,
    SourcingRun,
)
from .ports import ModelCall, get_provider
from .sourcing.guardrails import validate
from .sourcing.ports import SourceQuery
from .sourcing.sources import get_sources

ENRICH_SYSTEM = (
    "Ты — ассистент интернет-магазина инструментов. По данным из учётной системы "
    "1С сформируй структурированный контент карточки. Отвечай ТОЛЬКО валидным JSON "
    "без markdown и пояснений."
)


def _fallback() -> EnrichResult:
    return EnrichResult(
        name=None,
        short_description=None,
        description=None,
        attributes=[],
        confidence=0.0,
        source="fallback",
    )


def enrich(*, product_id: int, force: bool = False) -> EnrichResult:
    """Гибрид: детерминированный слой уже наполнил EAV; здесь LLM добивает
    карточный текст и пробелы. Запись — через catalog.enrichment (граница ADR).
    Любой сбой → fallback (деградация без исключения), всегда пишем AiCallLog.
    """
    product = get_enrichable_product(product_id)
    if product is None:
        AiCallLog.objects.create(
            capability=AiCallLog.Capability.ENRICH,
            status=AiCallLog.Status.ERROR,
            entity_ref=product_id,
            reason="product_not_found",
        )
        return _fallback()

    if product.content_locked and not force:
        AiCallLog.objects.create(
            capability=AiCallLog.Capability.ENRICH,
            status=AiCallLog.Status.FALLBACK,
            entity_ref=product_id,
            reason="content_locked",
        )
        return _fallback()

    provider = get_provider()
    user = (product.original_name or product.name or "").strip()
    call = ModelCall(system=ENRICH_SYSTEM, user=user)
    try:
        reply = provider.complete(call)
    except Exception as exc:  # noqa: BLE001 — деградация: любой сбой провайдера
        AiCallLog.objects.create(
            capability=AiCallLog.Capability.ENRICH,
            provider=getattr(provider, "name", ""),
            status=AiCallLog.Status.ERROR,
            entity_ref=product_id,
            reason=str(exc)[:255],
        )
        return _fallback()

    result = parse_enrich_output(reply.text)
    if result is None:
        AiCallLog.objects.create(
            capability=AiCallLog.Capability.ENRICH,
            provider=reply.provider,
            model=reply.model,
            status=AiCallLog.Status.FALLBACK,
            entity_ref=product_id,
            reason="invalid_output",
            tokens_in=reply.tokens_in,
            tokens_out=reply.tokens_out,
        )
        return _fallback()

    try:
        apply_ai_enrichment(
            product,
            name=result.name,
            short_description=result.short_description,
            description=result.description,
            attributes=[
                AiAttr(slug=a.slug, value=a.value, confidence=a.confidence)
                for a in result.attributes
            ],
            confidence=result.confidence,
            force=force,
        )
    except Exception as exc:  # noqa: BLE001 — деградация: сбой записи в каталог
        AiCallLog.objects.create(
            capability=AiCallLog.Capability.ENRICH,
            provider=reply.provider,
            model=reply.model,
            status=AiCallLog.Status.ERROR,
            entity_ref=product_id,
            reason=f"write_failed:{exc!s}"[:255],
        )
        return _fallback()
    AiCallLog.objects.create(
        capability=AiCallLog.Capability.ENRICH,
        provider=reply.provider,
        model=reply.model,
        status=AiCallLog.Status.OK,
        entity_ref=product_id,
        output=reply.text[:2000],
        tokens_in=reply.tokens_in,
        tokens_out=reply.tokens_out,
    )
    return result


DEFAULT_LIMIT = 8
MAX_LIMIT = 24
CANDIDATE_CAP = 300


@dataclass(frozen=True)
class Recommendation:
    """Одна рекомендация: id товара, человекочитаемая причина и тех. оценка.

    ``score`` — внутренняя релевантность подбора (чем выше, тем релевантнее);
    стабилен в рамках одного движка, но не является публичным числом для UI.
    """

    product_id: int
    reason: str
    score: float = 0.0


def recommend(*, query=None, context=None, limit: int = DEFAULT_LIMIT) -> list[Recommendation]:
    """ЕДИНЫЙ публичный контракт подбора рекомендаций (capability-срез).

    Вход → выход: ``query``/``context`` → ``list[Recommendation]``. В V1 якорь
    подбора берётся из ``context["product_id"]``; ``query`` зарезервирован под
    текстовый/LLM-движок и пока не используется. Внутренность (сейчас —
    детерминированный EAV ``_similar_by_eav``) заменяема без изменения сигнатуры.

    Возвращает ``[]`` на любом «нет данных»: пустой/невалидный context, неизвестный
    или скрытый якорь, ``limit <= 0``.
    """
    if limit <= 0:
        return []
    limit = min(limit, MAX_LIMIT)

    context = context or {}
    product_id = context.get("product_id")
    if not product_id:
        return []

    anchor = (
        visible_products()
        .filter(pk=product_id)
        .only("id", "category_id", "brand", "attrs_cache")
        .first()
    )
    if anchor is None:
        return []

    return _similar_by_eav(anchor, limit)


def _norm(value):
    """Нормализовать значение характеристики для сравнения.

    str → ``strip().lower()``; bool/int/float → как есть (boolean ``False`` НЕ
    теряется — это валидное значение); list → ``frozenset`` нормализованных
    непустых элементов; None/"" → ``None`` (маркер «пусто», в сравнении игнор).
    """
    if value is None:
        return None
    if isinstance(value, bool):  # до int — bool это подкласс int
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        return v or None
    if isinstance(value, int | float):
        return value
    if isinstance(value, list | tuple | set):
        normed = {n for n in (_norm(item) for item in value) if n is not None}
        return frozenset(normed) or None
    return value


def _overlap(anchor_attrs: dict, cand_attrs: dict) -> int:
    """Число совпадений характеристик якоря и кандидата по общим slug.

    Скаляры — равенство нормализованных значений (1 совпадение). Списки — размер
    пересечения нормализованных множеств. Пустые значения (None/"") не считаются.
    """
    if not anchor_attrs or not cand_attrs:
        return 0
    total = 0
    for slug, a_raw in anchor_attrs.items():
        if slug not in cand_attrs:
            continue
        a = _norm(a_raw)
        b = _norm(cand_attrs[slug])
        if a is None or b is None:
            continue
        if isinstance(a, frozenset) or isinstance(b, frozenset):
            a_set = a if isinstance(a, frozenset) else frozenset({a})
            b_set = b if isinstance(b, frozenset) else frozenset({b})
            total += len(a_set & b_set)
        elif a == b:
            total += 1
    return total


def _same_brand(anchor_brand, cand_brand) -> bool:
    """Совпадение брендов (регистронезависимо) и оба непустые."""
    a = (anchor_brand or "").strip().lower()
    b = (cand_brand or "").strip().lower()
    return bool(a) and a == b


def _in_stock(cand) -> bool:
    """В наличии: по остатку (>0), с фолбэком на stock_status, если остатка нет."""
    qty = cand.get("stock_quantity")
    if qty is not None:
        return qty > 0
    return cand.get("stock_status") == "in_stock"


def _similar_by_eav(product, limit: int) -> list[Recommendation]:
    """Детерминированный подбор «похожих» в той же категории по EAV-характеристикам.

    Кандидаты: видимые товары той же категории (кроме самого якоря), не более
    ``CANDIDATE_CAP`` по возрастанию id. Кандидат включается ТОЛЬКО при наличии
    сигнала (``overlap > 0`` или тот же бренд) — иначе это шум «просто та же
    категория». Сортировка детерминирована: по убыванию score, затем по id.
    """
    anchor_attrs = product.attrs_cache or {}
    anchor_brand = product.brand

    candidates = (
        visible_products()
        .filter(category_id=product.category_id)
        .exclude(pk=product.pk)
        .values("id", "brand", "stock_status", "stock_quantity", "attrs_cache")
        .order_by("id")[:CANDIDATE_CAP]
    )

    scored: list[Recommendation] = []
    for cand in candidates:
        overlap = _overlap(anchor_attrs, cand.get("attrs_cache") or {})
        same_brand = _same_brand(anchor_brand, cand.get("brand"))
        if overlap <= 0 and not same_brand:
            continue  # ни характеристик, ни бренда — отсекаем шум

        in_stock = _in_stock(cand)
        score = overlap * 10 + (3 if same_brand else 0) + (1 if in_stock else 0)
        if overlap > 0:
            reason = f"Похож по характеристикам: {overlap} совпадений"
        else:
            reason = "Та же категория, тот же бренд"
        scored.append(Recommendation(product_id=cand["id"], reason=reason, score=float(score)))

    scored.sort(key=lambda r: (-r.score, r.product_id))
    return scored[:limit]


# --- sourcing ---

MAX_CALL_COST = Decimal("1.0")  # верхняя граница одного вызова (резерв бюджета)


class BudgetExceeded(Exception):
    pass


def _today() -> _dt.date:
    return _dt.date.today()


def _norm_hash(value: dict) -> str:
    return hashlib.sha256(
        _json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _baseline_for(product, target_kind, attribute_slug):
    """Снимок (hash, source) целевого поля сейчас — для evidence."""
    if target_kind in provenance.TEXT_TARGETS:
        cur = getattr(product, target_kind) or ""
        src = (product.content_field_sources or {}).get(target_kind, "")
        return provenance.value_hash(cur), src
    return provenance.value_hash(None), ""  # атрибуты упрощённо «пусто» (детально — Task 8)


def source_content(*, product_id, sources=None, idempotency_key) -> SourcingRun:
    run, _ = SourcingRun.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults={"product_ref": product_id, "status": SourcingRun.Status.RUNNING},
    )
    product = get_enrichable_product(product_id)
    if product is None:
        run.status = SourcingRun.Status.ERROR
        run.save()
        return run
    if product.content_locked:
        run.status = SourcingRun.Status.DEGRADED
        run.save()
        return run

    adapters = sources if sources is not None else get_sources()
    if not adapters:
        run.status = SourcingRun.Status.CONFIGURATION_ERROR
        run.save()
        return run

    query = SourceQuery(
        article=getattr(product, "article", "") or "",
        name=product.original_name or product.name or "",
        brand=getattr(product, "brand", "") or "",
        category=product.category.slug if product.category_id else "",
        needed_targets=["description"],
    )
    any_ok = False
    for adapter in adapters:
        name = getattr(adapter, "name", "src")
        if ExternalCall.objects.filter(
            run=run, adapter=name, status=ExternalCall.Status.OK
        ).exists():
            any_ok = True
            continue
        try:
            call, owns = _reserve_and_open_call(run, name)
        except BudgetExceeded:
            run.status = SourcingRun.Status.DEGRADED
            break
        if not owns:  # #7: чужой running/unknown НЕ успех — только реально ok
            if call.status == ExternalCall.Status.OK:
                any_ok = True
            continue
        try:
            reply = adapter.find(query, idempotency_key=f"{idempotency_key}:{name}")
        except Exception:  # noqa: BLE001 — изоляция источника
            _close_call(call, ExternalCall.Status.ERROR)
            continue
        _persist_findings(call, product, reply)  # #7: находки ДО пометки ok
        _close_call(call, ExternalCall.Status.OK, reply=reply)
        any_ok = True

    if run.status == SourcingRun.Status.RUNNING:
        run.status = SourcingRun.Status.OK if any_ok else SourcingRun.Status.ERROR
    elif run.status == SourcingRun.Status.DEGRADED and any_ok:
        # Бюджет закончился после ≥1 успешного адаптера → апгрейд до OK.
        run.status = SourcingRun.Status.OK
    run.finished_at = timezone.now()
    run.save()
    return run


def _reserve_and_open_call(run, adapter):
    """Атомарно: владение попыткой + резерв бюджета + ExternalCall(running).
    Возврат (call, owns_attempt): сеть вызывает только владелец попытки."""
    with transaction.atomic():
        b, _ = SourcingBudget.objects.select_for_update().get_or_create(
            day=_today(), defaults={"daily_cap": Decimal("0")}
        )
        call = ExternalCall.objects.select_for_update().filter(run=run, adapter=adapter).first()
        if call and call.status in (
            ExternalCall.Status.RUNNING,
            ExternalCall.Status.OK,
            ExternalCall.Status.UNKNOWN,
        ):
            return call, False
        if b.spent + b.reserved + MAX_CALL_COST > b.daily_cap:
            raise BudgetExceeded
        b.reserved += MAX_CALL_COST
        b.save()
        if call is None:
            call = ExternalCall.objects.create(
                run=run,
                adapter=adapter,
                status=ExternalCall.Status.RUNNING,
                reserved_cost=MAX_CALL_COST,
                reserved_day=_today(),
                provider_idempotency_key=f"{run.idempotency_key}:{adapter}",
                attempt_count=1,
            )
        else:  # error → running (захват retry)
            call.status = ExternalCall.Status.RUNNING
            call.attempt_count += 1
            call.reserved_cost = MAX_CALL_COST
            call.reserved_day = _today()
            call.provider_idempotency_key = f"{run.idempotency_key}:{adapter}"
            call.save()
        return call, True


def _close_call(call, status, *, reply=None):
    with transaction.atomic():
        day = call.reserved_day or _today()  # #8: резерв снимаем со строки дня резервирования
        b, _ = SourcingBudget.objects.select_for_update().get_or_create(
            day=day, defaults={"daily_cap": Decimal("0")}
        )
        call.status = status
        call.finished_at = timezone.now()
        if reply is not None:
            call.provider = reply.provider
            call.tokens_in = reply.tokens_in
            call.tokens_out = reply.tokens_out
            call.cost = reply.cost
            call.http_status = reply.http_status
            call.raw_excerpt = reply.raw_excerpt[:4000]
        if status == ExternalCall.Status.OK:
            actual = min(reply.cost, call.reserved_cost) if reply else Decimal("0")  # #8: cap
            call.cost = actual
            b.spent += actual
            b.reserved -= call.reserved_cost
        elif status == ExternalCall.Status.ERROR:
            b.reserved -= call.reserved_cost  # definite-failed: резерв снимаем
        # unknown: резерв НЕ снимаем (§6.5 спеки)
        b.save()
        call.save()


def _persist_findings(call, product, reply):
    for raw in reply.findings:
        f = validate(raw)
        if f is None:
            continue
        nh = _norm_hash(f.value)
        finding, _ = ContentFinding.objects.get_or_create(
            product_ref=product.pk,
            target_kind=f.target_kind,
            attribute_slug=f.attribute_slug,
            normalized_hash=nh,
            defaults={
                "product_id": product.pk,
                "value": f.value,
                "source_name": f.source_name,
                "confidence": f.confidence,
                "status": ContentFinding.Status.PENDING,
            },
        )
        bh, bsrc = _baseline_for(product, f.target_kind, f.attribute_slug)
        FindingEvidence.objects.get_or_create(
            finding=finding,
            external_call=call,
            canonical_url=f.canonical_url,
            defaults={
                "source_name": f.source_name,
                "confidence": f.confidence,
                "observed_value_hash": bh,
                "observed_source": bsrc,
            },
        )


def approve_and_apply_finding(finding_id, evidence_id, reviewer_id):
    pre = (
        ContentFinding.objects.filter(pk=finding_id)
        .values("product_ref", "target_kind", "attribute_slug")
        .first()
    )
    if pre is None:
        return provenance.ApplyResult("missing_product")
    ev_obj = FindingEvidence.objects.filter(pk=evidence_id, finding_id=finding_id).first()
    if ev_obj is None:
        return provenance.ApplyResult("invalid", "evidence_not_found")
    attempt = FindingApplicationAttempt.objects.create(
        finding_id=finding_id,
        evidence_id=evidence_id,
        reviewer_id=reviewer_id,
        status=FindingApplicationAttempt.Status.CLAIMED,
    )
    try:
        with transaction.atomic():
            siblings = list(
                ContentFinding.objects.filter(
                    product_ref=pre["product_ref"],
                    target_kind=pre["target_kind"],
                    attribute_slug=pre["attribute_slug"],
                )
                .select_for_update()
                .order_by("pk")
            )
            by_id = {f.pk: f for f in siblings}
            f = by_id[finding_id]
            if f.status != ContentFinding.Status.PENDING:
                attempt.status = FindingApplicationAttempt.Status.DONE
                attempt.save()
                return provenance.ApplyResult("skipped", "already_processed")
            cmd = provenance.SourcedValueCommand(
                product_id=pre["product_ref"],
                target_kind=f.target_kind,
                attribute_slug=f.attribute_slug,
                value=f.value,
                source=ev_obj.source_name,
                confidence=ev_obj.confidence,
                observed_value_hash=ev_obj.observed_value_hash,
                observed_source=ev_obj.observed_source,
                allow_equal_override=True,
            )
            result = provenance.apply_sourced_value(cmd)
            if result.status == "applied":
                f.status = ContentFinding.Status.APPLIED
                f.applied_at = timezone.now()
                f.reviewed_by_id = reviewer_id
                f.reviewed_at = timezone.now()
                f.save()
                for other in siblings:
                    if other.pk != f.pk and other.status == ContentFinding.Status.APPLIED:
                        other.status = ContentFinding.Status.SUPERSEDED
                        other.save()
            else:
                f.last_outcome = result.status
                f.reviewed_by_id = reviewer_id
                f.reviewed_at = timezone.now()
                f.save()
            attempt.status = FindingApplicationAttempt.Status.DONE
            attempt.save()
            return result
    except Exception as exc:  # noqa: BLE001 — техническая ошибка → rollback всей txn
        with transaction.atomic():
            FindingApplicationAttempt.objects.filter(pk=attempt.pk).update(
                status=FindingApplicationAttempt.Status.FAILED
            )
            ContentFinding.objects.filter(
                pk=finding_id, status=ContentFinding.Status.PENDING
            ).update(last_outcome="apply_failed", rejection_reason=str(exc)[:255])
        raise


# ---------------------------------------------------------------------------
# ai_assist — контракт AI-консультанта (#74, V2 placeholder)
# ---------------------------------------------------------------------------


@dataclass
class AssistReply:
    """Ответ AI-консультанта. Контракт зафиксирован для V2-реализации.

    Поля:
    - text        — текст ответа (всегда заполнен, минимум заглушка)
    - suggestions — опциональные slug'и рекомендованных товаров
    - session_id  — идентификатор сессии для continuity
    - is_stub     — True если это заглушка (LLM не подключён)
    """

    text: str
    suggestions: list[str] = field(default_factory=list)
    session_id: str = ""
    is_stub: bool = False


def assist(*, message: str, session: str = "") -> AssistReply:
    """Ответить на вопрос покупателя (контракт AI-консультанта, #74).

    V1 — заглушка: возвращает предсказуемый placeholder, не обращается к LLM.
    V2 — LLM-реализация за портом (контракт остаётся неизменным).

    Args:
        message: сообщение покупателя
        session: идентификатор сессии (для continuity между запросами)

    Returns:
        AssistReply с текстом и опциональными рекомендациями товаров
    """
    return AssistReply(
        text=(
            "Здравствуйте! Я пока работаю в тестовом режиме. "
            "По вопросам подбора инструмента свяжитесь с нами по телефону."
        ),
        suggestions=[],
        session_id=session or "",
        is_stub=True,
    )
