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
# En operación principal (depósito/honorarios) solo imputan 1000/29 o 1/15 con cuota elegida.
CONCEPTOS_ALQUILER_LEGACY_SIN_CUOTA_OBJETIVO = frozenset({'1', '15'})


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


def lineas_imputables_desde_movimiento(movimiento, *, operacion_principal: bool = False) -> list:
    """
    Líneas del movimiento que pueden marcar cuotas.
    No usa mes_alquiler_importe del JSON raíz (solo referencia de recibo).
    En operación principal no imputa concepto 1/15 sin cuota_objetivo_id (evita marcar meses
    por el valor oculto «mes alquiler» o líneas de alquiler no cobradas en el recibo).
    """
    lineas = payload_conceptos_desde_movimiento_detalle(movimiento)
    out = []
    for it in lineas:
        cid_raw = it.get('id')
        if cid_raw is None:
            cid_raw = it.get('codigo')
        cid = _normalizar_codigo_concepto_caja(cid_raw)
        if cid not in CODIGOS_IMPUTACION_ALQUILER_CUOTA:
            continue
        imp = parse_decimal_monto(it.get('importe'))
        if imp <= 0:
            continue
        if operacion_principal:
            raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
            if cid in CONCEPTOS_CUOTA_OBJETIVO:
                out.append(it)
            elif cid in CONCEPTOS_ALQUILER_LEGACY_SIN_CUOTA_OBJETIVO and raw_qid.isdigit():
                out.append(it)
            continue
        out.append(it)
    return out


def movimiento_tiene_lineas_imputables_cuota(movimiento, *, operacion_principal: bool = False) -> bool:
    return len(lineas_imputables_desde_movimiento(movimiento, operacion_principal=operacion_principal)) > 0


def revertir_cuota_imputacion(cuota, contrato, hoy=None) -> None:
    """Quita cobro imputado a la cuota y revierte crédito propagado a cuotas posteriores."""
    from django.utils import timezone as tz

    from inmobiliaria.models.contrato import CuotaMensual

    hoy = hoy or tz.now().date()
    if cuota.estado not in ('pagada', 'pagada_con_mora'):
        return
    nk = int(cuota.numero_cuota)
    revertir_credito_propagado_por_cuota_annulada(contrato, nk)
    cuota.movimiento = None
    cuota.fecha_pago = None
    cuota.credito_aplicado = Decimal('0')
    cuota.credito_origen_numero_cuota = None
    if cuota.fecha_vencimiento and cuota.fecha_vencimiento < hoy:
        cuota.estado = 'vencida'
    else:
        cuota.estado = 'pendiente'
    cuota.save(
        update_fields=[
            'movimiento',
            'fecha_pago',
            'credito_aplicado',
            'credito_origen_numero_cuota',
            'estado',
        ]
    )


def desimputar_cuotas_de_movimiento(contrato, movimiento, hoy=None, *, forzar: bool = False) -> int:
    """
    Revierte cuotas marcadas pagadas por un movimiento que no tenía líneas de alquiler/cuota
    imputables (p. ej. solo depósito 10 y honorarios 25).
    """
    from django.utils import timezone as tz

    hoy = hoy or tz.now().date()
    if not forzar and movimiento_tiene_lineas_imputables_cuota(movimiento, operacion_principal=False):
        return 0
    n = 0
    for cq in contrato.cuotas.filter(movimiento=movimiento).order_by('numero_cuota'):
        if cq.estado in ('pagada', 'pagada_con_mora'):
            revertir_cuota_imputacion(cq, contrato, hoy=hoy)
            n += 1
    return n


def marcar_cuota_pagada_totalmente_cubierta_por_credito(cuota, movimiento, hoy) -> None:
    """Si el saldo llegó a cero solo por credito_aplicado, marca la cuota pagada."""
    from django.utils import timezone as tz

    hoy = hoy or tz.now().date()
    if cuota.estado not in ('pendiente', 'vencida'):
        return
    if cuota.saldo_para_cobro() > Decimal('0.05'):
        return
    obligacion = Decimal(str(cuota.monto_total or 0))
    if obligacion <= 0:
        return
    fecha_pago = hoy
    if movimiento is not None and getattr(movimiento, 'fecha', None):
        fecha_pago = movimiento.fecha
    elif cuota.credito_origen_numero_cuota:
        orig = (
            cuota.contrato.cuotas.filter(numero_cuota=cuota.credito_origen_numero_cuota)
            .values('fecha_pago', 'movimiento_id')
            .first()
        )
        if orig and orig.get('fecha_pago'):
            fecha_pago = orig['fecha_pago']
    if movimiento is None and cuota.credito_origen_numero_cuota:
        orig_cuota = (
            cuota.contrato.cuotas.filter(numero_cuota=cuota.credito_origen_numero_cuota)
            .select_related('movimiento')
            .first()
        )
        if orig_cuota and orig_cuota.movimiento_id:
            movimiento = orig_cuota.movimiento
    cuota.estado = 'pagada'
    cuota.fecha_pago = fecha_pago
    if movimiento is not None:
        cuota.movimiento = movimiento
    cuota.monto_base = obligacion
    cuota.monto_total = obligacion
    cuota.recargo_mora = Decimal('0')
    cuota.descuento = Decimal('0')
    cuota.credito_aplicado = Decimal('0')
    cuota.credito_origen_numero_cuota = None
    update_fields = [
        'estado',
        'fecha_pago',
        'monto_base',
        'monto_total',
        'recargo_mora',
        'descuento',
        'credito_aplicado',
        'credito_origen_numero_cuota',
    ]
    if movimiento is not None:
        update_fields.append('movimiento')
    cuota.save(update_fields=update_fields)


def sincronizar_cuotas_totalmente_cubiertas_por_credito(contrato, hoy=None, *, movimiento_fallback=None) -> int:
    """
    Corrige cuotas pendientes/vencidas cuyo saldo ya es cero por crédito/advance total.
    Devuelve la cantidad de cuotas marcadas pagadas.
    """
    from django.utils import timezone as tz

    tol = Decimal('0.05')
    hoy = hoy or tz.now().date()
    n = 0
    for cuota in contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).order_by('numero_cuota'):
        cuota.refresh_from_db()
        if cuota.saldo_para_cobro() > tol:
            continue
        cred = Decimal(str(cuota.credito_aplicado or 0))
        if cred <= tol:
            continue
        mov = movimiento_fallback
        if mov is None and cuota.credito_origen_numero_cuota:
            orig = (
                cuota.contrato.cuotas.filter(numero_cuota=cuota.credito_origen_numero_cuota)
                .select_related('movimiento')
                .first()
            )
            if orig and orig.movimiento_id:
                mov = orig.movimiento
        marcar_cuota_pagada_totalmente_cubierta_por_credito(cuota, mov, hoy)
        n += 1
    return n


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
            if (
                movimiento is not None
                and sig.estado in ('pendiente', 'vencida')
                and sig.saldo_para_cobro() <= tol
                and cred > tol
            ):
                marcar_cuota_pagada_totalmente_cubierta_por_credito(sig, movimiento, hoy)
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


def aplicar_adelanto_parcial_cuota(
    cuota,
    importe: Decimal,
    movimiento,
    hoy,
    origen_numero_cuota: int | None = None,
) -> None:
    """
    Abono parcial a una cuota pendiente/vencida (concepto 29/1000 con importe menor al saldo).
    Suma en credito_aplicado sin marcar la cuota como pagada.
    """
    tol = Decimal('0.05')
    importe = Decimal(str(importe or 0))
    if importe <= tol:
        return
    if cuota.estado not in ('pendiente', 'vencida'):
        raise ValueError(f'La cuota {cuota.numero_cuota} no admite adelanto en estado {cuota.estado}.')
    saldo = cuota.saldo_para_cobro()
    if importe > saldo + tol:
        raise ValueError(
            f'El importe {importe} supera el saldo a cobrar ({saldo}) de la cuota {cuota.numero_cuota}.'
        )
    cred = Decimal(str(cuota.credito_aplicado or 0))
    cuota.credito_aplicado = cred + importe
    if origen_numero_cuota is not None:
        cuota.credito_origen_numero_cuota = int(origen_numero_cuota)
    cuota.save(update_fields=['credito_aplicado', 'credito_origen_numero_cuota'])
    cuota.refresh_from_db()
    if cuota.saldo_para_cobro() <= tol:
        marcar_cuota_pagada_totalmente_cubierta_por_credito(cuota, movimiento, hoy)


def imputar_importe_a_cuota(
    cuota,
    cubierto: Decimal,
    movimiento,
    hoy,
    *,
    origen_numero_cuota: int | None = None,
) -> str:
    """
    Imputa un importe a una cuota: pago total (y excedente a siguientes) o adelanto parcial.
    Devuelve 'pagada', 'adelanto' o 'sin_cambio'.
    """
    tol = Decimal('0.05')
    cubierto = Decimal(str(cubierto or 0))
    if cubierto <= tol:
        return 'sin_cambio'
    saldo = cuota.saldo_para_cobro()
    if cubierto + tol >= saldo:
        marcar_cuota_pagada_con_excedente_a_favor(cuota, cubierto, movimiento, hoy)
        return 'pagada'
    aplicar_adelanto_parcial_cuota(cuota, cubierto, movimiento, hoy, origen_numero_cuota)
    return 'adelanto'


def marcar_cuota_pagada_con_excedente_a_favor(cuota, cubierto: Decimal, movimiento, hoy) -> None:
    """
    Marca la cuota pagada registrando el importe de obligación (monto_total actual),
    limpia mora/descuento en el registro y propaga cubierto - saldo a la siguiente cuota.
    Solo usar cuando el importe cubre el saldo completo; para parciales usar imputar_importe_a_cuota.
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


def imputar_cuotas_mensuales_desde_movimiento_1000(
    contrato, movimiento, *, operacion_principal: bool = False
) -> int:
    """
    Marca pagadas las cuotas pendientes/vencidas según líneas de alquiler/cuota del movimiento
    (conceptos 1000, 29, 1 o 15; ARS o USD), por cuota_objetivo_id o en orden de numero_cuota.
    Devuelve la cantidad de cuotas afectadas (pagadas o adelanto).
    """
    lineas_imputables = lineas_imputables_desde_movimiento(
        movimiento, operacion_principal=operacion_principal
    )

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
    ultima_cuota_pagada_num = None
    for cq in cuotas_pendientes:
        cq.refresh_from_db()
        cubierto = asignado_por_cuota.get(cq.id, Decimal('0'))
        if cubierto <= tol_q:
            continue
        origen = ultima_cuota_pagada_num if ultima_cuota_pagada_num is not None else int(cq.numero_cuota)
        resultado = imputar_importe_a_cuota(
            cq, cubierto, movimiento, hoy_q, origen_numero_cuota=origen
        )
        if resultado == 'pagada':
            ultima_cuota_pagada_num = int(cq.numero_cuota)
            n += 1
        elif resultado == 'adelanto':
            n += 1
    sincronizar_cuotas_totalmente_cubiertas_por_credito(contrato, hoy_q, movimiento_fallback=movimiento)
    return n


def payload_raiz_desde_movimiento_detalle(movimiento) -> dict:
    """Objeto JSON raíz de concepto_detalle (p. ej. pago_cuota_mensual + cuota_id)."""
    raw = (getattr(movimiento, 'concepto_detalle', None) or '').strip().lstrip('\ufeff')
    if not raw or not raw.startswith('{'):
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}


def movimiento_imputa_cuota(movimiento, cuota, *, operacion_principal: bool = False) -> bool:
    """True si el movimiento registró cobro (total o parcial) imputado a esta cuota."""
    cuota_id = int(cuota.id)
    numero = int(cuota.numero_cuota)
    contrato_id = int(cuota.contrato_id)

    payload = payload_raiz_desde_movimiento_detalle(movimiento)
    if payload.get('pago_cuota_mensual') and int(payload.get('cuota_id') or 0) == cuota_id:
        return True

    for it in lineas_imputables_desde_movimiento(movimiento, operacion_principal=operacion_principal):
        raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
        if raw_qid.isdigit() and int(raw_qid) == cuota_id:
            return True

    concepto = getattr(movimiento, 'concepto', None) or ''
    if f'Contrato #{contrato_id} — Cuota {numero}/' in concepto:
        return True
    if f'Cuota {numero}/' in concepto and f'Contrato #{contrato_id}' in concepto:
        return True
    return False


def movimientos_recibo_por_cuota(cuota, movimientos_iterable) -> list:
    """Movimientos de caja con recibo imputados a esta cuota (incluye adelantos parciales)."""
    vistos: set[int] = set()
    result = []
    for mov in movimientos_iterable:
        if movimiento_imputa_cuota(mov, cuota):
            mid = int(mov.id)
            if mid not in vistos:
                vistos.add(mid)
                result.append(mov)
    if cuota.movimiento_id and int(cuota.movimiento_id) not in vistos:
        mov_final = getattr(cuota, 'movimiento', None)
        if mov_final is not None:
            result.append(mov_final)
    result.sort(key=lambda m: (m.fecha, m.id))
    return result


def mapa_movimientos_recibo_por_cuota_id(cuotas, movimientos_iterable) -> dict[int, list]:
    return {int(c.id): movimientos_recibo_por_cuota(c, movimientos_iterable) for c in cuotas}
