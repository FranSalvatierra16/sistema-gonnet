from decimal import Decimal

from django.db import migrations, models


def migrar_montos_inicio(apps, schema_editor):
    Inicio = apps.get_model('inmobiliaria', 'InicioCajaLibroPropiedad')
    for row in Inicio.objects.all():
        ars = Decimal(str(getattr(row, 'monto_ars', 0) or 0))
        usd = Decimal(str(getattr(row, 'monto_usd', 0) or 0))
        if ars >= 0:
            row.alquileres_ars = ars
            row.gastos_ars = Decimal('0')
        else:
            row.gastos_ars = abs(ars)
            row.alquileres_ars = Decimal('0')
        if usd >= 0:
            row.ingreso_usd = usd
            row.gastos_usd = Decimal('0')
        else:
            row.gastos_usd = abs(usd)
            row.ingreso_usd = Decimal('0')
        row.save(
            update_fields=['gastos_ars', 'alquileres_ars', 'gastos_usd', 'ingreso_usd']
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0169_cotizacionlibrooperacion'),
    ]

    operations = [
        migrations.AddField(
            model_name='iniciocajalibropropiedad',
            name='gastos_ars',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=14,
                verbose_name='Gastos ARS (inicio)',
            ),
        ),
        migrations.AddField(
            model_name='iniciocajalibropropiedad',
            name='alquileres_ars',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=14,
                verbose_name='Alquileres ARS (inicio)',
            ),
        ),
        migrations.AddField(
            model_name='iniciocajalibropropiedad',
            name='gastos_usd',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=14,
                verbose_name='Gastos USD (inicio)',
            ),
        ),
        migrations.AddField(
            model_name='iniciocajalibropropiedad',
            name='ingreso_usd',
            field=models.DecimalField(
                decimal_places=2, default=Decimal('0'), max_digits=14,
                verbose_name='Ingreso USD (inicio)',
            ),
        ),
        migrations.AddField(
            model_name='iniciocajalibropropiedad',
            name='tipo_cambio',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=14,
                null=True,
                verbose_name='Tipo de cambio (inicio)',
            ),
        ),
        migrations.RunPython(migrar_montos_inicio, noop_reverse),
        migrations.RemoveField(
            model_name='iniciocajalibropropiedad',
            name='monto_ars',
        ),
        migrations.RemoveField(
            model_name='iniciocajalibropropiedad',
            name='monto_usd',
        ),
    ]
