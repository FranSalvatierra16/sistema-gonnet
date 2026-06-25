from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def recalcular_monto_a_pagar_sin_cochera(apps, schema_editor):
    LiquidacionPropietario = apps.get_model('inmobiliaria', 'LiquidacionPropietario')
    GastoPropietario = apps.get_model('inmobiliaria', 'GastoPropietario')

    for liq in LiquidacionPropietario.objects.exclude(estado='cancelada').iterator():
        gastos = (
            GastoPropietario.objects.filter(liquidacion_id=liq.id, aceptado=True).aggregate(
                total=Sum('monto')
            )['total']
            or Decimal('0')
        )
        prop = liq.monto_propietario or Decimal('0')
        fondo = liq.monto_fondo_mantenimiento or Decimal('0')
        neto = prop - gastos - fondo
        liq.monto_gastos = gastos
        liq.monto_a_pagar = neto if neto > 0 else Decimal('0')
        liq.save(update_fields=['monto_gastos', 'monto_a_pagar'])


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0135_reserva_alquiler_sindicato'),
    ]

    operations = [
        migrations.RunPython(recalcular_monto_a_pagar_sin_cochera, migrations.RunPython.noop),
    ]
