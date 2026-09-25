"""Платёж становится провайдер-агностичным + поля фискализации (АТОЛ Pay).

Переименование, а не «удалить/создать»: платежи ЮKassa (если такие есть) должны
пережить смену кассы — их идентификаторы остаются на месте под новыми именами.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("payments", "0002_alter_payment_status_refund")]

    operations = [
        migrations.RenameField(
            model_name="payment", old_name="yookassa_id", new_name="provider_payment_id"
        ),
        migrations.RenameField(
            model_name="refund", old_name="yookassa_refund_id", new_name="provider_refund_id"
        ),
        migrations.AlterField(
            model_name="payment",
            name="provider_payment_id",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="ID платежа в кассе",
            ),
        ),
        migrations.AlterField(
            model_name="refund",
            name="provider_refund_id",
            field=models.CharField(blank=True, max_length=64, verbose_name="ID возврата в кассе"),
        ),
        migrations.AddField(
            model_name="payment",
            name="provider",
            field=models.CharField(
                choices=[("atolpay", "АТОЛ Pay"), ("yookassa", "ЮKassa")],
                db_index=True,
                default="atolpay",
                max_length=16,
                verbose_name="Касса",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="provider_order_id",
            field=models.CharField(
                blank=True,
                help_text=(
                    "orderId, отправленный в кассу. Только ASCII: номер заказа с "
                    "кириллической «П» касса не принимает, поэтому у платежа свой "
                    "идентификатор."
                ),
                max_length=64,
                null=True,
                unique=True,
                verbose_name="Номер заказа для кассы",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt_id",
            field=models.CharField(blank=True, max_length=64, verbose_name="ID чека"),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt_status",
            field=models.CharField(
                blank=True,
                help_text="success / fail — из callback type=fiscal.",
                max_length=16,
                verbose_name="Статус фискализации",
            ),
        ),
        migrations.AddField(
            model_name="payment",
            name="receipt_error",
            field=models.TextField(blank=True, verbose_name="Ошибка фискализации"),
        ),
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[
                    ("atolpay", "АТОЛ Pay (карта/СБП)"),
                    ("yookassa", "ЮKassa (карта/СБП)"),
                    ("invoice", "Счёт (B2B)"),
                    ("cash", "При получении"),
                ],
                default="atolpay",
                max_length=20,
                verbose_name="Способ оплаты",
            ),
        ),
    ]
