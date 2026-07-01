from django.db import models
from django.utils.translation import gettext_lazy as _


class AiCallLog(models.Model):
    """Журнал каждого обращения к модели (ARCHITECTURE-AI §6).

    Пишется всегда — включая fallback и error. FK на чужие модели нет:
    связь с доменом — через ``entity_ref`` (например product_id).
    """

    class Capability(models.TextChoices):
        ENRICH = "enrich", _("Обогащение")
        RECOMMEND = "recommend", _("Рекомендации")
        ASSIST = "assist", _("Ассистент")

    class Status(models.TextChoices):
        OK = "ok", _("Успех")
        FALLBACK = "fallback", _("Фолбэк")
        ERROR = "error", _("Ошибка")

    capability = models.CharField(max_length=12, choices=Capability.choices, db_index=True)
    provider = models.CharField(max_length=32, blank=True)
    model = models.CharField(max_length=64, blank=True)
    input_ref = models.CharField(max_length=255, blank=True)
    output = models.JSONField(null=True, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=5, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=8, choices=Status.choices, db_index=True)
    reason = models.CharField(max_length=255, blank=True)
    entity_ref = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Вызов AI")
        verbose_name_plural = _("Журнал вызовов AI")
        indexes = [models.Index(fields=["capability", "status"])]

    def __str__(self) -> str:
        return f"{self.capability}/{self.status} #{self.entity_ref or '-'}"


class SourcingRun(models.Model):
    """Один логический запуск source_content() по товару (аудит)."""

    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        DEGRADED = "degraded"
        CONFIGURATION_ERROR = "configuration_error"
        ERROR = "error"

    idempotency_key = models.CharField(max_length=128, unique=True)
    product_ref = models.PositiveIntegerField(db_index=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.RUNNING)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"SourcingRun#{self.pk} product={self.product_ref} [{self.status}]"


class ExternalCall(models.Model):
    """Один вызов источника (web|marketplace). Телеметрия и аудит оплаты."""

    class Status(models.TextChoices):
        RUNNING = "running"
        OK = "ok"
        ERROR = "error"
        UNKNOWN = "unknown"

    run = models.ForeignKey(SourcingRun, on_delete=models.CASCADE, related_name="calls")
    adapter = models.CharField(max_length=16)
    provider = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RUNNING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    provider_idempotency_key = models.CharField(max_length=128, blank=True)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reserved_cost = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reserved_day = models.DateField(null=True, blank=True)  # #8: день резерва бюджета
    latency_ms = models.PositiveIntegerField(default=0)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    raw_excerpt = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "adapter"], name="uniq_externalcall_run_adapter")
        ]

    def __str__(self) -> str:
        return f"ExternalCall#{self.pk} adapter={self.adapter} [{self.status}]"


class ContentFinding(models.Model):
    """Дедуп-канон значения для (product, target). Агрегаты — для отображения."""

    class Status(models.TextChoices):
        PENDING = "pending"
        APPLIED = "applied"
        REJECTED = "rejected"
        SUPERSEDED = "superseded"

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    product_ref = models.PositiveIntegerField(db_index=True)
    target_kind = models.CharField(max_length=20)
    attribute_slug = models.CharField(max_length=120, blank=True, default="")
    value = models.JSONField()
    normalized_hash = models.CharField(max_length=64)
    source_name = models.CharField(max_length=16)
    confidence = models.FloatField(default=0.0)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    last_outcome = models.CharField(max_length=24, blank=True)
    selected_evidence = models.ForeignKey(
        "FindingEvidence", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["product_ref", "target_kind", "attribute_slug", "normalized_hash"],
                name="uniq_finding_dedup",
            ),
            models.CheckConstraint(
                name="finding_attribute_slug_consistency",
                check=(models.Q(target_kind="attribute") & ~models.Q(attribute_slug=""))
                | (~models.Q(target_kind="attribute") & models.Q(attribute_slug="")),
            ),
        ]
        indexes = [models.Index(fields=["product_ref", "status"])]

    def __str__(self) -> str:
        return f"ContentFinding#{self.pk} product={self.product_ref} {self.target_kind} [{self.status}]"


class FindingEvidence(models.Model):
    """Подтверждение факта (вызов + url + baseline на момент наблюдения)."""

    finding = models.ForeignKey(ContentFinding, on_delete=models.CASCADE, related_name="evidences")
    external_call = models.ForeignKey(ExternalCall, on_delete=models.PROTECT, related_name="+")
    source_name = models.CharField(max_length=16)
    confidence = models.FloatField(default=0.0)
    observed_value_hash = models.CharField(max_length=64)
    observed_source = models.CharField(max_length=16, blank=True)
    canonical_url = models.URLField(max_length=500, blank=True)
    observed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["finding", "external_call", "canonical_url"], name="uniq_evidence"
            )
        ]

    def __str__(self) -> str:
        return f"FindingEvidence#{self.pk} finding={self.finding_id}"


class FindingApplicationAttempt(models.Model):
    """Committed-claim попытки применения (создаётся ДО основной транзакции)."""

    class Status(models.TextChoices):
        CLAIMED = "claimed"
        DONE = "done"
        FAILED = "failed"

    finding = models.ForeignKey(ContentFinding, on_delete=models.CASCADE, related_name="attempts")
    evidence = models.ForeignKey(FindingEvidence, on_delete=models.PROTECT, related_name="+")
    reviewer = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CLAIMED)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["finding"],
                condition=models.Q(status="claimed"),
                name="uniq_active_claim_per_finding",
            )
        ]

    def __str__(self) -> str:
        return f"FindingApplicationAttempt#{self.pk} finding={self.finding_id} [{self.status}]"


class SourcingBudget(models.Model):
    """Атомарная защита дневного бюджета от параллельных workers."""

    day = models.DateField(unique=True)
    daily_cap = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    reserved = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    spent = models.DecimalField(max_digits=10, decimal_places=4, default=0)

    def __str__(self) -> str:
        return f"SourcingBudget {self.day} cap={self.daily_cap}"
