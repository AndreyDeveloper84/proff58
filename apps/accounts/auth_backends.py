"""Вход на витрине — по e-mail.

Стандартный ModelBackend проверяет USERNAME_FIELD, а он у нас телефон: это
техническое поле для админки и MAX, покупатель им не пользуется. Здесь тот же
ModelBackend, но ищущий человека по почте.

Телефон как способ входа не поддерживается намеренно: на витрине его больше не
спрашивают. Кто зарегистрирован через MAX и почты не указывал, входит через MAX.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailBackend(ModelBackend):
    """Аутентификация по паре «e-mail + пароль»."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        # DRF и формы Django кладут идентификатор в username; свой вызов —
        # authenticate(email=...). Принимаем оба, чтобы вызывающему было всё равно.
        email = kwargs.get("email") or username
        if not email or not password:
            return None

        try:
            # Регистр в адресах значения не имеет: человек, заведший Ivan@..,
            # завтра наберёт ivan@.. и должен войти.
            user = User.objects.get(email__iexact=email.strip())
        except User.DoesNotExist:
            # Хеширование впустую — чтобы по времени ответа нельзя было
            # отличить «нет такого адреса» от «неверный пароль».
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # Уникальность гарантирует constraint; сюда можно попасть только на
            # базе, где остались дубли из прежней схемы. Вход не даём.
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
