from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0170_inicio_caja_cuatro_columnas'),
    ]

    operations = [
        migrations.CreateModel(
            name='CostosCompraLibroPropiedad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'valor_depto_comprado',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0'),
                        max_digits=14,
                        verbose_name='Valor depto comprado (USD)',
                    ),
                ),
                (
                    'gastos_escritura',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0'),
                        max_digits=14,
                        verbose_name='Gastos de escritura (USD)',
                    ),
                ),
                (
                    'honorarios_pagados',
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal('0'),
                        max_digits=14,
                        verbose_name='Honorarios pagados (USD)',
                    ),
                ),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                (
                    'actualizado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='costos_compra_libro_actualizados',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'propiedad',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='costos_compra_libro',
                        to='inmobiliaria.propiedad',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Costos de compra libro propiedad',
                'verbose_name_plural': 'Costos de compra libro propiedad',
            },
        ),
    ]
