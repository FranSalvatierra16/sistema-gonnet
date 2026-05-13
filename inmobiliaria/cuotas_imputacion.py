"""
Imputación de CuotaMensual desde líneas concepto 1000 (ARS o USD) guardadas en MovimientoCaja.concepto_detalle.
Usado en operación principal y en reparaciones por management command.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from .decimal_utils import parse_decimal_monto

logger = logging.getLogger(__name__)

CODIGOS_IMPUTACION_ALQUILER_CUOTA = frozenset({'1000', '1', '15'})


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


def imputar_cuotas_mensuales_desde_movimiento_1000(contrato, movimiento) -> int:
    """
    Marca pagadas las cuotas pendientes/vencidas según líneas de alquiler/cuota del movimiento
    (conceptos 1000, 1 o 15; ARS o USD), por cuota_objetivo_id o en orden de numero_cuota.
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
        cubierto = asignado_por_cuota.get(cq.id, Decimal('0'))
        objetivo = Decimal(str(cq.monto_total or 0))
        if cubierto > 0 and cubierto + tol_q >= objetivo:
            cq.estado = 'pagada'
            cq.fecha_pago = hoy_q
            cq.movimiento = movimiento
            cq.monto_base = cubierto
            cq.monto_total = cubierto
            cq.recargo_mora = Decimal('0')
            cq.descuento = Decimal('0')
            cq.save()
            n += 1
    return n
