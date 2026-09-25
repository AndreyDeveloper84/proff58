import datetime as dt

import pytest
from django.db import IntegrityError, transaction

from apps.ai.models import (
    ContentFinding,
    ExternalCall,
    FindingApplicationAttempt,
    FindingEvidence,
    SourcingBudget,
    SourcingRun,
)


@pytest.mark.django_db
def test_external_call_unique_per_run_adapter():
    run = SourcingRun.objects.create(idempotency_key="k1", product_ref=1, status="running")
    ExternalCall.objects.create(run=run, adapter="web", status="running")
    with pytest.raises(IntegrityError), transaction.atomic():
        ExternalCall.objects.create(run=run, adapter="web", status="running")


@pytest.mark.django_db
def test_finding_dedup_unique():
    f = dict(
        product_ref=1,
        target_kind="description",
        attribute_slug="",
        value={"type": "text", "value": "x"},
        normalized_hash="h1",
        source_name="web",
        confidence=0.9,
        status="pending",
    )
    ContentFinding.objects.create(**f)
    with pytest.raises(IntegrityError), transaction.atomic():
        ContentFinding.objects.create(**f)


@pytest.mark.django_db
def test_attribute_slug_check_constraint():
    with pytest.raises(IntegrityError), transaction.atomic():
        ContentFinding.objects.create(
            product_ref=1,
            target_kind="attribute",
            attribute_slug="",
            value={},
            normalized_hash="h2",
            source_name="web",
            confidence=0.1,
            status="pending",
        )


@pytest.mark.django_db
def test_one_active_claim_per_finding():
    f = ContentFinding.objects.create(
        product_ref=1,
        target_kind="description",
        attribute_slug="",
        value={"type": "text", "value": "x"},
        normalized_hash="h3",
        source_name="web",
        confidence=0.9,
        status="pending",
    )
    run = SourcingRun.objects.create(idempotency_key="k2", product_ref=1, status="ok")
    call = ExternalCall.objects.create(run=run, adapter="web", status="ok")
    ev = FindingEvidence.objects.create(
        finding=f,
        external_call=call,
        source_name="web",
        confidence=0.9,
        observed_value_hash="b",
        observed_source="",
        canonical_url="https://x/y",
    )
    FindingApplicationAttempt.objects.create(finding=f, evidence=ev, status="claimed")
    with pytest.raises(IntegrityError), transaction.atomic():
        FindingApplicationAttempt.objects.create(finding=f, evidence=ev, status="claimed")


@pytest.mark.django_db
def test_budget_unique_day():
    SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=10)
    with pytest.raises(IntegrityError), transaction.atomic():
        SourcingBudget.objects.create(day=dt.date(2026, 6, 29), daily_cap=20)
