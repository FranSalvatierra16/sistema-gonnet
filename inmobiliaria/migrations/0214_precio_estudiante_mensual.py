from decimal import Decimal

from django.db import migrations


def corregir_total_estudiante(apps, schema_editor):
    """El modal de precios multiplicaba la tarifa Estudiante (mensual) por 15/16 días."""
    Precio = apps.get_model('inmobiliaria', 'Precio')
    for p in Precio.objects.filter(tipo_precio='ESTUDIANTE', precio_por_dia__gt=0, precio_total__gt=0):
        por_mes = Decimal(str(p.precio_por_dia))
        total = Decimal(str(p.precio_total))
        aj = Decimal(str(p.ajuste_porcentaje or 0)) / Decimal('100')
        for factor in {Decimal('1') + aj, Decimal('1') - aj}:
            esperado_mes = por_mes * factor
            if any(abs(total - esperado_mes * dias) < Decimal('1') for dias in (15, 16)):
                p.precio_total = esperado_mes.quantize(Decimal('0.01'))
                p.save(update_fields=['precio_total'])
                break


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0213_comision_eliminada_manual'),
    ]

    operations = [
        migrations.RunPython(corregir_total_estudiante, migrations.RunPython.noop),
    ]
