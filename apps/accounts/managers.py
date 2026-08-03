"""Менеджер пользователей.

Идентификаторов два, и оба необязательные по отдельности: покупатель с витрины
приходит с e-mail (логин) и без телефона, из MAX — наоборот, с телефоном и без
почты. Требуем хотя бы один: аккаунт, к которому нельзя обратиться ни одним
способом, завести нельзя.

Суперпользователь — по телефону: ``createsuperuser`` спрашивает USERNAME_FIELD,
и админка вход по телефону сохраняет.
"""

from django.contrib.auth.models import BaseUserManager
from django.db import transaction

from apps.core.events import user_registered


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, phone, password, **extra_fields):
        email = extra_fields.pop("email", "")
        if email:
            email = self.normalize_email(email)
        if not phone and not email:
            raise ValueError("Нужен телефон или e-mail — иначе к аккаунту не обратиться")
        # Пустой телефон храним как NULL: '' нарушил бы уникальность со второго
        # же покупателя, зарегистрированного по почте.
        user = self.model(phone=phone or None, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, phone=None, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        user = self._create_user(phone, password, **extra_fields)
        # Доменное событие — после коммита; в payload только id (подписчик перечитает).
        transaction.on_commit(
            lambda uid=user.pk: user_registered.send(sender=type(user), user_id=uid)
        )
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Телефон обязателен для суперпользователя — это его логин в админке")
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Суперпользователь должен иметь is_staff=True")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Суперпользователь должен иметь is_superuser=True")
        return self._create_user(phone, password, **extra_fields)
