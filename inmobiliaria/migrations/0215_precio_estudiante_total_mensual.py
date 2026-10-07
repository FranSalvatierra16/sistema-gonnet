from decimal import ROUND_HALF_UP, Decimal

from django.db import migrations


def total_estudiante_igual_al_mensual(apps, schema_editor):
    """Estudiante: precio_total = precio mensual (con ajuste), como calcula Precio.save()."""
    Precio = apps.get_model('inmobiliaria', 'Precio')
    for p in Precio.objects.filter(tipo_precio='ESTUDIANTE', precio_por_dia__isnull=False):
        por_mes = Decimal(str(p.precio_por_dia))
        aj = Decimal(str(p.ajuste_porcentaje or 0))
        total = por_mes * (1 - aj / Decimal('100')) if aj else por_mes
        total = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if p.precio_total is None or Decimal(str(p.precio_total)) != total:
            Precio.objects.filter(pk=p.pk).update(precio_total=total)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0214_precio_estudiante_mensual'),
    ]

    operations = [
        migrations.RunPython(total_estudiante_igual_al_mensual, migrations.RunPython.noop),
    ]
