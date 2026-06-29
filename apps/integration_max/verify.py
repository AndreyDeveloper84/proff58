"""Верификация подписей MAX Bot API."""

from __future__ import annotations

import hashlib
import hmac


def verify_contact_hash(token: str, vcf_info: str, received_hash: str) -> bool:
    """Проверить HMAC-SHA256 подпись контакта от MAX.

    MAX передаёт vcf_info с экранированными \\r\\n — перед хешированием
    заменяем на реальные переносы строк.
    """
    if not token or not vcf_info or not received_hash:
        return False
    vcf_bytes = vcf_info.replace("\\r\\n", "\r\n").encode("utf-8")
    expected = hmac.new(token.encode("utf-8"), vcf_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_hash)


def extract_phone_from_vcf(vcf_info: str) -> str | None:
    """Извлечь телефон из vCard строки."""
    for line in vcf_info.replace("\\r\\n", "\r\n").splitlines():
        if line.startswith("TEL"):
            parts = line.split(":")
            if len(parts) >= 2:
                phone = parts[-1].strip()
                if not phone.startswith("+"):
                    phone = "+" + phone
                return phone
    return None
