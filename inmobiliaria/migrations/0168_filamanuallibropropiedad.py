from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0167_iniciocajalibropropiedad'),
    ]

    operations = [
        migrations.CreateModel(
            name='FilaManualLibroPropiedad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField()),
                ('descripcion', models.CharField(blank=True, default='', max_length=255)),
                ('gastos_ars', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('alquileres_ars', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('gastos_usd', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                ('ingreso_usd', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=14)),
                (
                    'tipo_cambio',
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        max_digits=14,
                        null=True,
                        verbose_name='Tipo de cambio',
                    ),
                ),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                (
                    'creado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='filas_manuales_libro_creadas',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'propiedad',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='filas_manuales_libro',
                        to='inmobiliaria.propiedad',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Fila manual libro propiedad',
                'verbose_name_plural': 'Filas manuales libro propiedad',
                'ordering': ['fecha', 'id'],
            },
        ),
    ]
