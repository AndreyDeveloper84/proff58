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
