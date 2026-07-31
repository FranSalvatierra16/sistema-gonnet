import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0168_filamanuallibropropiedad'),
    ]

    operations = [
        migrations.CreateModel(
            name='CotizacionLibroOperacion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                (
                    'cotizacion_dolar',
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                        verbose_name='Tipo de cambio (ARS por USD)',
                    ),
                ),
                ('actualizado_en', models.DateTimeField(auto_now=True)),
                (
                    'actualizado_por',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='cotizaciones_libro_operacion',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    'reserva',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cotizacion_libro',
                        to='inmobiliaria.reserva',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Cotización libro operación',
                'verbose_name_plural': 'Cotizaciones libro operación',
            },
        ),
    ]
