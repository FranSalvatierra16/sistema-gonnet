from decimal import Decimal
import re

from django.db import migrations
from django.db.models import Q


def _monto_total_mov(m):
    return (
        Decimal(str(getattr(m, 'monto_efectivo', 0) or 0))
        + Decimal(str(getattr(m, 'monto_cheque', 0) or 0))
        + Decimal(str(getattr(m, 'monto_tarjeta', 0) or 0))
        + Decimal(str(getattr(m, 'monto_deposito', 0) or 0))
    )


def _pagado_primera_operacion(movs_contrato):
    if not movs_contrato:
        return Decimal('0')

    ordenados = sorted(
        movs_contrato,
        key=lambda x: ((getattr(x, 'fecha', None) or 0), (getattr(x, 'id', None) or 0)),
    )
    primero = ordenados[0]
    interno = (getattr(primero, 'numero_liquidacion', None) or '').strip()
    if interno:
        return sum(
            (
                _monto_total_mov(m)
                for m in ordenados
                if (getattr(m, 'numero_liquidacion', None) or '').strip() == interno
            ),
            Decimal('0'),
        )
    return _monto_total_mov(primero)


def backfill_neto_a_posesion(apps, schema_editor):
    ContratoAlquiler = apps.get_model('inmobiliaria', 'ContratoAlquiler')
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')

    contratos = list(
        ContratoAlquiler.objects.all().only(
            'id',
            'precio_mensual',
            'honorarios_referencia',
            'sellados_referencia',
            'neto_a_posesion_referencia',
        )
    )
    if not contratos:
        return

    contrato_ids = [c.id for c in contratos]

    movs = list(
        MovimientoCaja.objects.filter(
            tipo='ingreso',
        )
        .filter(
            Q(concepto__icontains='Contrato #') | Q(concepto__icontains='Contrato#')
        )
        .only(
            'id',
            'fecha',
            'concepto',
            'numero_liquidacion',
            'monto_efectivo',
            'monto_cheque',
            'monto_tarjeta',
            'monto_deposito',
        )
    )

    movs_por_contrato = {}
    for m in movs:
        concepto = getattr(m, 'concepto', None) or ''
        match = re.search(r'Contrato\s*#\s*(\d+)', concepto, re.IGNORECASE)
        if not match:
            continue
        cid = int(match.group(1))
        if cid in contrato_ids:
            movs_por_contrato.setdefault(cid, []).append(m)

    actualizados = []
    for c in contratos:
        base_operacion_inicial = (
            Decimal(str(getattr(c, 'precio_mensual', 0) or 0))
            + Decimal(str(getattr(c, 'honorarios_referencia', 0) or 0))
            + Decimal(str(getattr(c, 'sellados_referencia', 0) or 0))
        )
        pagado_operacion_inicial = _pagado_primera_operacion(movs_por_contrato.get(c.id, []))
        neto = base_operacion_inicial - pagado_operacion_inicial
        if neto < 0:
            neto = Decimal('0')

        if Decimal(str(getattr(c, 'neto_a_posesion_referencia', 0) or 0)) != neto:
            c.neto_a_posesion_referencia = neto
            actualizados.append(c)

    if actualizados:
        ContratoAlquiler.objects.bulk_update(actualizados, ['neto_a_posesion_referencia'], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0109_contratoalquiler_neto_a_posesion_referencia'),
    ]

    operations = [
        migrations.RunPython(backfill_neto_a_posesion, migrations.RunPython.noop),
    ]
