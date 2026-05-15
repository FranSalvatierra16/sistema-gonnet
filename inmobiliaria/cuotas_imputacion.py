"""
Imputación de CuotaMensual desde líneas de concepto de alquiler/cuota (1000, 29, 1 o 15)
guardadas en MovimientoCaja.concepto_detalle.
Usado en operación principal y en reparaciones por management command.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from .decimal_utils import parse_decimal_monto

logger = logging.getLogger(__name__)

# Conceptos cuyo importe se imputa a una CuotaMensual (con cuota_objetivo_id o en orden).
CODIGOS_IMPUTACION_ALQUILER_CUOTA = frozenset({'1000', '1', '15', '29'})
# Igual que 1000: exigen elegir cuota objetivo en operaciones de cobro de cuota.
CONCEPTOS_CUOTA_OBJETIVO = frozenset({'1000', '29'})


def _normalizar_codigo_concepto_caja(cid_raw) -> str:
    if cid_raw is None or cid_raw == '':
        return ''
    if isinstance(cid_raw, bool):
        return ''
    if isinstance(cid_raw, int):
        return str(cid_raw)
    if isinstance(cid_raw, float):
        if cid_raw != cid_raw:  # NaN
            return ''
        if cid_raw == int(cid_raw):
            return str(int(cid_raw))
    s = str(cid_raw).strip()
    try:
        if s and s.replace('.', '', 1).replace('-', '', 1).isdigit() and '.' in s:
            f = float(s)
            if f == int(f):
                return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s


def payload_conceptos_desde_movimiento_detalle(movimiento) -> list:
    """Lista de dicts de conceptos desde concepto_detalle (objeto con 'conceptos', array raíz o vacío)."""
    raw = (getattr(movimiento, 'concepto_detalle', None) or '').strip().lstrip('\ufeff')
    if not raw:
        return []
    try:
        if raw.startswith('{'):
            data = json.loads(raw)
            if isinstance(data, dict):
                return list(data.get('conceptos') or [])
            return []
        if raw.startswith('['):
            data = json.loads(raw)
            return list(data) if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning('JSON concepto_detalle inválido movimiento_id=%s: %s', getattr(movimiento, 'id', None), e)
    return []


def marcar_cuota_pagada_totalmente_cubierta_por_credito(cuota, movimiento, hoy) -> None:
    """Si el saldo llegó a cero solo por credito_aplicado, marca la cuota pagada (mismo movimiento que originó el crédito)."""
    from django.utils import timezone as tz

    hoy = hoy or tz.now().date()
    if cuota.estado not in ('pendiente', 'vencida'):
        return
    if cuota.saldo_para_cobro() > Decimal('0.05'):
        return
    obligacion = Decimal(str(cuota.monto_total or 0))
    if obligacion <= 0:
        return
    cuota.estado = 'pagada'
    cuota.fecha_pago = hoy
    cuota.movimiento = movimiento
    cuota.monto_base = obligacion
    cuota.monto_total = obligacion
    cuota.recargo_mora = Decimal('0')
    cuota.descuento = Decimal('0')
    cuota.credito_aplicado = Decimal('0')
    cuota.credito_origen_numero_cuota = None
    cuota.save(
        update_fields=[
            'estado',
            'fecha_pago',
            'movimiento',
            'monto_base',
            'monto_total',
            'recargo_mora',
            'descuento',
            'credito_aplicado',
            'credito_origen_numero_cuota',
        ]
    )


def revertir_credito_propagado_por_cuota_annulada(contrato, numero_cuota_origen: int) -> int:
    """
    Quita credito_aplicado en cuotas posteriores que quedó imputado al excedente del cobro de la cuota N.
    Devuelve la cantidad de filas actualizadas.
    """
    from inmobiliaria.models.contrato import CuotaMensual

    nk = int(numero_cuota_origen)
    return CuotaMensual.objects.filter(
        contrato=contrato,
        estado__in=['pendiente', 'vencida'],
        numero_cuota__gt=nk,
        credito_origen_numero_cuota=nk,
    ).update(credito_aplicado=Decimal('0'), credito_origen_numero_cuota=None)


def propagar_credito_excedente_cuotas(contrato, despues_de_numero_cuota: int, exceso: Decimal, movimiento, hoy) -> None:
    """
    Reparte el excedente de un cobro (pago mayor al saldo de la cuota) en credito_aplicado
    de las cuotas siguientes (pendiente/vencida), sin superar el saldo de cada una.
    """
    tol = Decimal('0.02')
    if exceso <= tol:
        return
    rest = exceso
    nk = int(despues_de_numero_cuota)
    sigs = contrato.cuotas.filter(
        numero_cuota__gt=nk,
        estado__in=['pendiente', 'vencida'],
    ).order_by('numero_cuota')
    for sig in sigs:
        if rest <= tol:
            break
        tot = Decimal(str(sig.monto_total or 0))
        cred = Decimal(str(sig.credito_aplicado or 0))
        cap = max(Decimal('0'), tot - cred)
        if cap <= tol:
            continue
        add = min(rest, cap)
        sig.credito_aplicado = cred + add
        if add > tol:
            sig.credito_origen_numero_cuota = nk
            sig.save(update_fields=['credito_aplicado', 'credito_origen_numero_cuota'])
        else:
            sig.save(update_fields=['credito_aplicado'])
        rest -= add
        sig.refresh_from_db()
        if movimiento is not None and sig.estado in ('pendiente', 'vencida') and sig.saldo_para_cobro() <= tol:
            marcar_cuota_pagada_totalmente_cubierta_por_credito(sig, movimiento, hoy)


def marcar_cuota_pagada_con_excedente_a_favor(cuota, cubierto: Decimal, movimiento, hoy) -> None:
    """
    Marca la cuota pagada registrando el importe de obligación (monto_total actual),
    limpia mora/descuento en el registro y propaga cubierto - saldo a la siguiente cuota.
    """
    tol = Decimal('0.05')
    saldo = cuota.saldo_para_cobro()
    if cubierto + tol < saldo:
        raise ValueError(
            f'La cuota {cuota.numero_cuota} requiere al menos {saldo} y el importe imputado es {cubierto}.'
        )
    obligacion = Decimal(str(cuota.monto_total or 0))
    exceso = cubierto - saldo
    cuota.estado = 'pagada'
    cuota.fecha_pago = hoy
    cuota.movimiento = movimiento
    cuota.monto_base = obligacion
    cuota.monto_total = obligacion
    cuota.recargo_mora = Decimal('0')
    cuota.descuento = Decimal('0')
    cuota.credito_aplicado = Decimal('0')
    cuota.credito_origen_numero_cuota = None
    cuota.save()
    if exceso > tol:
        propagar_credito_excedente_cuotas(cuota.contrato, cuota.numero_cuota, exceso, movimiento, hoy)


def imputar_cuotas_mensuales_desde_movimiento_1000(contrato, movimiento) -> int:
    """
    Marca pagadas las cuotas pendientes/vencidas según líneas de alquiler/cuota del movimiento
    (conceptos 1000, 29, 1 o 15; ARS o USD), por cuota_objetivo_id o en orden de numero_cuota.
    Devuelve la cantidad de cuotas guardadas como pagadas.
    """
    lineas = payload_conceptos_desde_movimiento_detalle(movimiento)
    lineas_imputables = []
    for it in lineas:
        cid_raw = it.get('id')
        if cid_raw is None:
            cid_raw = it.get('codigo')
        cid = _normalizar_codigo_concepto_caja(cid_raw)
        if cid not in CODIGOS_IMPUTACION_ALQUILER_CUOTA:
            continue
        imp = parse_decimal_monto(it.get('importe'))
        if imp > 0:
            lineas_imputables.append(it)

    if not lineas_imputables:
        return 0

    tol_q = Decimal('0.05')
    monto_lineas = sum(parse_decimal_monto(it.get('importe')) for it in lineas_imputables)
    monto_ya_imputado = Decimal('0')
    for cq in contrato.cuotas.filter(movimiento=movimiento, estado__in=['pagada', 'pagada_con_mora']):
        monto_ya_imputado += Decimal(str(cq.monto_total or 0))
    if monto_ya_imputado > 0 and monto_ya_imputado + tol_q >= monto_lineas:
        return 0

    cuotas_pendientes = list(
        contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).order_by('numero_cuota')
    )
    if not cuotas_pendientes:
        return 0

    cuotas_by_id = {c.id: c for c in cuotas_pendientes}
    asignado_por_cuota: dict[int, Decimal] = {}
    idx_primera_pendiente = 0

    for it in lineas_imputables:
        imp = parse_decimal_monto(it.get('importe'))
        raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
        cuota_target = None
        if raw_qid.isdigit():
            cuota_target = cuotas_by_id.get(int(raw_qid))
        if not cuota_target:
            while idx_primera_pendiente < len(cuotas_pendientes):
                cnd = cuotas_pendientes[idx_primera_pendiente]
                idx_primera_pendiente += 1
                if cnd.estado in ('pendiente', 'vencida'):
                    cuota_target = cnd
                    break
        if not cuota_target:
            break
        prev = asignado_por_cuota.get(cuota_target.id, Decimal('0'))
        asignado_por_cuota[cuota_target.id] = prev + imp

    from django.utils import timezone

    hoy_q = timezone.now().date()
    n = 0
    for cq in cuotas_pendientes:
        cq.refresh_from_db()
        cubierto = asignado_por_cuota.get(cq.id, Decimal('0'))
        saldo = cq.saldo_para_cobro()
        if cubierto > 0 and cubierto + tol_q >= saldo:
            marcar_cuota_pagada_con_excedente_a_favor(cq, cubierto, movimiento, hoy_q)
            n += 1
    return n
