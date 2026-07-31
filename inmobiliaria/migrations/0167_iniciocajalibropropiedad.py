import datetime
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _fecha_inicio_caja_default():
    return datetime.date(2026, 6, 7)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0166_reserva_liq_monto_cochera_inquilino'),
    ]

    operations = [
        migrations.CreateModel(
            name='InicioCajaLibroPropiedad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'fecha',
                    models.DateField(
                        default=_fecha_inicio_caja_default,
                        help_text='Por defecto 07/06/2026.',
                        verbose_name='Fecha inicio de caja',
                    ),
                ),
                (
                    'monto_ars',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0'),
                        max_digits=14,
                        verbose_name='Inicio de caja ARS',
                    ),
                ),
                (
                    'monto_usd',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0'),
                        max_digits=14,
                        verbose_name='Inicio de caja USD',
                    ),
                ),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                (
                    'actualizado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='inicios_caja_libro_actualizados',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'propiedad',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='inicio_caja_libro',
                        to='inmobiliaria.propiedad',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Inicio de caja libro propiedad',
                'verbose_name_plural': 'Inicios de caja libro propiedad',
            },
        ),
    ]
