# Recrea liquidaciones canceladas para reservas anuladas cuya liquidación fue eliminada
# (honorarios de oficina: ingreso + reversión al anular).

from decimal import Decimal

from django.db import migrations
from django.utils import timezone


def _liquidaciones_reserva(reserva, LiquidacionPropietario):
    rid = int(reserva.pk)
    candidatas = list(LiquidacionPropietario.objects.filter(reserva_id=rid))
    vistos = {liq.pk for liq in candidatas}
    qs_extra = LiquidacionPropietario.objects.exclude(pk__in=vistos)
    if reserva.sucursal_id:
        qs_extra = qs_extra.filter(sucursal_id=reserva.sucursal_id)
    for liq in qs_extra.only('id', 'operaciones_incluidas').iterator(chunk_size=200):
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            if (op.get('tipo') or '').lower() != 'reserva':
                continue
            try:
                if int(op.get('id')) == rid:
                    candidatas.append(liq)
                    vistos.add(liq.pk)
                    break
            except (TypeError, ValueError):
                continue
    return candidatas


def _montos_reserva(reserva):
    total = Decimal(str(reserva.precio_total or 0))
    if total <= Decimal('0.01'):
        return None
    propiedad = reserva.propiedad
    pct = getattr(propiedad, 'porcentaje_propietario', None)
    if pct is None or pct <= 0:
        pct = Decimal('70')
    else:
        pct = Decimal(str(pct))
    prop = (total * pct / Decimal('100')).quantize(Decimal('0.01'))
    inm = (total - prop).quantize(Decimal('0.01'))
    if reserva.liq_monto_propietario is not None:
        prop = Decimal(str(reserva.liq_monto_propietario)).quantize(Decimal('0.01'))
    if reserva.liq_monto_inmobiliaria is not None:
        inm = Decimal(str(reserva.liq_monto_inmobiliaria)).quantize(Decimal('0.01'))
    coch = Decimal(str(reserva.liq_monto_cochera or 0))
    fondo = Decimal(str(reserva.liq_monto_fondo or 0))
    return total, prop, inm, coch, fondo


def _inferir_fecha_liquidacion(reserva, MovimientoCaja):
    rid = int(reserva.pk)
    if reserva.propiedad_id:
        movs = MovimientoCaja.objects.filter(
            propiedad_id=reserva.propiedad_id,
            tipo='EG',
            fecha_eliminacion__isnull=False,
        ).order_by('-fecha_eliminacion', '-fecha')
        for mov in movs[:30]:
            texto = f'{mov.concepto or ""} {mov.concepto_detalle or ""} {mov.numero_liquidacion or ""}'
            if str(rid) in texto:
                fc = mov.fecha
                if fc:
                    return fc
    if reserva.fecha_eliminacion:
        return reserva.fecha_eliminacion
    if reserva.fecha_inicio:
        from datetime import datetime, time

        return timezone.make_aware(datetime.combine(reserva.fecha_inicio, time(12, 0)))
    return timezone.now()


def recrear_liquidaciones_canceladas(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    LiquidacionPropietario = apps.get_model('inmobiliaria', 'LiquidacionPropietario')
    MovimientoCaja = apps.get_model('inmobiliaria', 'MovimientoCaja')

    qs = Reserva.objects.filter(eliminada=True, fecha_eliminacion__isnull=False).select_related(
        'propiedad', 'propiedad__propietario', 'sucursal'
    )
    for reserva in qs.iterator(chunk_size=100):
        if _liquidaciones_reserva(reserva, LiquidacionPropietario):
            continue
        montos = _montos_reserva(reserva)
        if not montos:
            continue
        total, prop, inm, coch, fondo = montos
        if inm <= Decimal('0.01') and coch <= Decimal('0.01') and fondo <= Decimal('0.01'):
            continue
        if not reserva.propiedad_id or not reserva.propiedad.propietario_id:
            continue

        fecha_liq = _inferir_fecha_liquidacion(reserva, MovimientoCaja)
        fecha_anul = reserva.fecha_eliminacion or timezone.now()

        liq = LiquidacionPropietario.objects.create(
            propietario_id=reserva.propiedad.propietario_id,
            propiedad_id=reserva.propiedad_id,
            reserva_id=reserva.id,
            estado='cancelada',
            moneda='ARS',
            monto_total_operacion=total,
            monto_propietario=prop,
            monto_inmobiliaria=inm,
            monto_cochera=coch,
            monto_fondo_mantenimiento=fondo,
            monto_gastos=Decimal('0'),
            monto_a_pagar=prop - fondo,
            fecha_desde=reserva.fecha_inicio,
            fecha_hasta=reserva.fecha_fin,
            observaciones=(
                f'[Migración 0151] Liquidación reconstruida — reserva #{reserva.id} anulada '
                f'(honorarios oficina).'
            ),
            operaciones_incluidas=[{'tipo': 'reserva', 'id': reserva.id}],
            sucursal_id=reserva.sucursal_id,
            fecha_procesamiento=fecha_anul,
        )
        LiquidacionPropietario.objects.filter(pk=liq.pk).update(fecha_creacion=fecha_liq)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0150_sucursal_vacaciones_invierno'),
    ]

    operations = [
        migrations.RunPython(recrear_liquidaciones_canceladas, noop),
    ]
