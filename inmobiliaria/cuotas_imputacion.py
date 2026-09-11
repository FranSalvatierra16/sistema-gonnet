"""
Imputación de CuotaMensual desde líneas de concepto de alquiler/cuota
guardadas en MovimientoCaja.concepto_detalle.
Usado en operación principal y en reparaciones por management command.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal

from .decimal_utils import parse_decimal_monto

logger = logging.getLogger(__name__)

# Conceptos cuyo importe se imputa a una CuotaMensual (con cuota_objetivo_id, mes en obs, o en orden).
# 1290 / 1010 = «Alquiler a Cobrar»; 100 = Saldo Locación; 1200 = Pago a cuenta (legacy).
CODIGOS_IMPUTACION_ALQUILER_CUOTA = frozenset({
    '1000', '1', '15', '29', '1290', '100', '1010', '1200',
})
# Exigen elegir cuota objetivo en operaciones de cobro de cuota.
CONCEPTOS_CUOTA_OBJETIVO = frozenset({'1000', '29', '1290', '1010', '1200'})
# En operación principal (depósito/honorarios) solo imputan 1000/29/1290 o 1/15 con cuota elegida.
CONCEPTOS_ALQUILER_LEGACY_SIN_CUOTA_OBJETIVO = frozenset({'1', '15', '100'})

MESES_ES = {
    'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
    'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
    'noviembre': 11, 'diciembre': 12,
}


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


def texto_linea_concepto(it) -> str:
    """Observaciones + nombre de una línea de concepto (para detectar mes / a cuenta)."""
    parts = [
        it.get('observaciones') or '',
        it.get('obs') or '',
        it.get('detalle') or '',
        it.get('detalle_l2') or '',
        it.get('nombre') or '',
        it.get('concepto') or '',
    ]
    return ' '.join(str(p) for p in parts if p).strip()


def mes_anio_desde_texto(texto: str) -> tuple[int | None, int | None]:
    """Extrae mes y año de textos tipo «A CUENTA AGOSTO 2026» / «SALDO JUNIO 2026»."""
    t = (texto or '').lower()
    if not t:
        return None, None
    mes_n = None
    for nombre, num in MESES_ES.items():
        if nombre in t:
            mes_n = num
            break
    m_anio = re.search(r'(20\d{2})', t)
    anio_n = int(m_anio.group(1)) if m_anio else None
    return mes_n, anio_n


def linea_es_imputacion_alquiler_cuota(it) -> bool:
    """True si la línea debe imputarse al plan de cuotas (código o nombre legacy)."""
    cid = _normalizar_codigo_concepto_caja(it.get('id') if it.get('id') is not None else it.get('codigo'))
    if cid in CODIGOS_IMPUTACION_ALQUILER_CUOTA:
        return True
    nom = (it.get('nombre') or it.get('concepto') or '').strip().lower()
    if not nom:
        return False
    claves = (
        'alquiler a cobrar',
        'pago a cuenta',
        'a cuenta',
        'saldo locaci',
        'saldo alquiler',
        'saldo de locaci',
    )
    return any(k in nom for k in claves)


def resolver_cuota_por_mes_texto(contrato, texto: str, cuotas=None):
    """Busca la cuota del contrato cuyo vencimiento coincide con el mes/año del texto."""
    mes_n, anio_n = mes_anio_desde_texto(texto)
    if mes_n is None:
        return None
    candidatas = list(cuotas) if cuotas is not None else list(
        contrato.cuotas.all().order_by('numero_cuota')
    )
    for c in candidatas:
        fv = getattr(c, 'fecha_vencimiento', None)
        if not fv or int(fv.month) != int(mes_n):
            continue
        if anio_n is not None and int(fv.year) != int(anio_n):
            continue
        return c
    if anio_n is not None:
        for c in candidatas:
            fv = getattr(c, 'fecha_vencimiento', None)
            if fv and int(fv.month) == int(mes_n):
                return c
    return None


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
        if not linea_es_imputacion_alquiler_cuota(it):
            continue
        cid = _normalizar_codigo_concepto_caja(it.get('id') if it.get('id') is not None else it.get('codigo'))
        imp = parse_decimal_monto(it.get('importe'))
        if imp <= 0:
            continue
        if operacion_principal:
            raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
            if cid in CONCEPTOS_CUOTA_OBJETIVO or (not cid and linea_es_imputacion_alquiler_cuota(it)):
                out.append(it)
            elif cid in CONCEPTOS_ALQUILER_LEGACY_SIN_CUOTA_OBJETIVO and raw_qid.isdigit():
                out.append(it)
            elif mes_anio_desde_texto(texto_linea_concepto(it))[0] is not None:
                # «A CUENTA AGOSTO» etc. aunque sea código legacy
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
    """
    Ya no marca como pagada una cuota cubierta solo por excedente de otro mes.
    El crédito permanece como adelanto; el mes se marca pagado recién con un cobro
    explícito de esa cuota (evita que agosto muestre el recibo de julio).
    """
    return


def sincronizar_cuotas_totalmente_cubiertas_por_credito(contrato, hoy=None, *, movimiento_fallback=None) -> int:
    """
    Repara cuotas mal marcadas como pagadas por excedente de otro cobro
    (mismo movimiento de caja sin línea/objetivo de esa cuota).
    Devuelve la cantidad de cuotas revertidas.
    """
    return reparar_cuotas_pagadas_solo_por_excedente(contrato, hoy=hoy)


def cuota_cubierta_solo_por_credito(cuota) -> bool:
    """True si la cuota sigue pendiente/vencida pero el crédito ya cubre el total."""
    if cuota.estado not in ('pendiente', 'vencida'):
        return False
    tol = Decimal('0.05')
    obligacion = Decimal(str(cuota.monto_total or 0))
    if obligacion <= tol:
        return False
    cred = Decimal(str(cuota.credito_aplicado or 0))
    return cred + tol >= obligacion and cuota.saldo_para_cobro() <= tol


def reparar_cuotas_pagadas_solo_por_excedente(contrato, hoy=None) -> int:
    """
    Si varias cuotas quedaron «pagadas» con el mismo movimiento y el recibo
    solo corresponde a una (u otra se marcó por excedente), deja pagada la
    correcta y vuelve las demás a pendiente/vencida.
    """
    from collections import defaultdict

    from django.utils import timezone as tz

    hoy = hoy or tz.now().date()
    n = 0
    por_mov: dict[int, list] = defaultdict(list)
    for cuota in (
        contrato.cuotas.filter(estado__in=['pagada', 'pagada_con_mora'], movimiento__isnull=False)
        .select_related('movimiento')
        .order_by('numero_cuota')
    ):
        por_mov[int(cuota.movimiento_id)].append(cuota)

    for mov_id, grupo in por_mov.items():
        mov = grupo[0].movimiento
        keep_ids = _cuota_ids_a_conservar_en_movimiento(mov, grupo)
        for c in grupo:
            if int(c.id) in keep_ids:
                continue
            _revertir_pagada_a_credito(c, None, hoy)
            n += 1
    return n


def _cuota_ids_a_conservar_en_movimiento(movimiento, grupo) -> set[int]:
    """Qué cuotas del grupo realmente cobró este recibo (el resto fue por excedente)."""
    grupo = sorted(grupo, key=lambda c: int(c.numero_cuota))
    if len(grupo) <= 1:
        return {int(grupo[0].id)} if grupo else set()

    explicit: set[int] = set()
    for c in grupo:
        if movimiento_imputa_cuota(movimiento, c):
            explicit.add(int(c.id))
    if explicit:
        return explicit

    lineas = lineas_imputables_desde_movimiento(movimiento, operacion_principal=False)
    n_lineas = len(lineas)
    if n_lineas <= 0:
        # Sin líneas claras: conservar solo la primera (menor número).
        return {int(grupo[0].id)}
    # Una línea por cuota en orden; el resto del grupo es excedente.
    keep_n = min(n_lineas, len(grupo))
    return {int(c.id) for c in grupo[:keep_n]}


def _revertir_pagada_a_credito(cuota, origen_numero_cuota, hoy) -> None:
    """Saca el estado pagado erróneo; no inventa crédito por el total del mes."""
    cuota.estado = (
        'vencida'
        if cuota.fecha_vencimiento and cuota.fecha_vencimiento < hoy
        else 'pendiente'
    )
    cuota.fecha_pago = None
    cuota.movimiento = None
    cuota.credito_aplicado = Decimal('0')
    cuota.credito_origen_numero_cuota = None
    cuota.recargo_mora = Decimal('0')
    cuota.descuento = Decimal('0')
    cuota.save(
        update_fields=[
            'estado',
            'fecha_pago',
            'movimiento',
            'credito_aplicado',
            'credito_origen_numero_cuota',
            'recargo_mora',
            'descuento',
        ]
    )


def revertir_credito_propagado_por_cuota_annulada(contrato, numero_cuota_origen: int) -> int:
    """
    Quita credito_aplicado en cuotas posteriores del cobro de la cuota N.
    También deshace cuotas que quedaron «pagadas» solo por ese excedente.
    """
    from django.utils import timezone as tz

    from inmobiliaria.models.contrato import CuotaMensual

    nk = int(numero_cuota_origen)
    hoy = tz.now().date()
    n = CuotaMensual.objects.filter(
        contrato=contrato,
        estado__in=['pendiente', 'vencida'],
        numero_cuota__gt=nk,
        credito_origen_numero_cuota=nk,
    ).update(credito_aplicado=Decimal('0'), credito_origen_numero_cuota=None)

    origen = (
        contrato.cuotas.filter(numero_cuota=nk).select_related('movimiento').first()
    )
    mov_id = origen.movimiento_id if origen else None
    for cq in contrato.cuotas.filter(
        estado__in=['pagada', 'pagada_con_mora'],
        numero_cuota__gt=nk,
    ).select_related('movimiento'):
        if mov_id and cq.movimiento_id == mov_id and not movimiento_imputa_cuota(cq.movimiento, cq):
            revertir_cuota_imputacion(cq, contrato, hoy=hoy)
            n += 1
        elif cq.credito_origen_numero_cuota == nk:
            revertir_cuota_imputacion(cq, contrato, hoy=hoy)
            n += 1
    return n


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
        # No marcar la siguiente como pagada: el excedente queda como adelanto.


def aplicar_adelanto_parcial_cuota(
    cuota,
    importe: Decimal,
    movimiento,
    hoy,
    origen_numero_cuota: int | None = None,
) -> None:
    """
    Abono parcial a una cuota pendiente/vencida (concepto 29/1000 con importe menor al saldo).
    Si con este abono el saldo llega a cero, marca la cuota pagada (cobro explícito de esa cuota).
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
        # Completó esta cuota con abonos explícitos a ella (no excedente de otro mes).
        from django.utils import timezone as tz

        hoy = hoy or tz.now().date()
        fecha_pago = hoy
        if movimiento is not None and getattr(movimiento, 'fecha', None):
            fecha_pago = movimiento.fecha
        obligacion = Decimal(str(cuota.monto_total or 0))
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
        fields = [
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
            fields.append('movimiento')
        cuota.save(update_fields=fields)


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
    Marca pagadas / adelanto las cuotas según líneas de alquiler/a cuenta del movimiento.
    Resuelve el mes por cuota_objetivo_id o por texto en observaciones («A CUENTA AGOSTO 2026»).
    """
    lineas_imputables = lineas_imputables_desde_movimiento(
        movimiento, operacion_principal=operacion_principal
    )

    if not lineas_imputables:
        return 0

    tol_q = Decimal('0.05')
    cuotas_todas = list(contrato.cuotas.all().order_by('numero_cuota'))
    cuotas_pendientes = [c for c in cuotas_todas if c.estado in ('pendiente', 'vencida')]
    if not cuotas_pendientes:
        return 0

    cuotas_by_id = {c.id: c for c in cuotas_pendientes}
    asignado_por_cuota: dict[int, Decimal] = {}
    idx_primera_pendiente = 0

    for it in lineas_imputables:
        imp = parse_decimal_monto(it.get('importe'))
        if imp <= tol_q:
            continue
        texto = texto_linea_concepto(it)
        raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
        cuota_target = None
        if raw_qid.isdigit():
            cuota_target = cuotas_by_id.get(int(raw_qid))

        if not cuota_target:
            # «SALDO JUNIO» / «A CUENTA AGOSTO 2026» → mes correcto (no la primera pendiente).
            cuota_por_mes = resolver_cuota_por_mes_texto(contrato, texto, cuotas_todas)
            if cuota_por_mes is not None:
                if cuota_por_mes.estado in ('pagada', 'pagada_con_mora'):
                    # Ese mes ya está cerrado; no volcar el importe al siguiente pendiente.
                    continue
                if cuota_por_mes.estado in ('pendiente', 'vencida'):
                    cuota_target = cuota_por_mes

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
        # Evitar duplicar si este movimiento ya dejó adelanto en la cuota.
        if (
            Decimal(str(cq.credito_aplicado or 0)) + tol_q >= cubierto
            and movimiento_imputa_cuota(movimiento, cq)
        ):
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
    cached = getattr(movimiento, '_cache_payload_raiz_detalle', None)
    if cached is not None:
        return cached
    raw = (getattr(movimiento, 'concepto_detalle', None) or '').strip().lstrip('\ufeff')
    if not raw or not raw.startswith('{'):
        movimiento._cache_payload_raiz_detalle = {}
        return {}
    try:
        data = json.loads(raw)
        out = data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        out = {}
    movimiento._cache_payload_raiz_detalle = out
    return out


def movimiento_imputa_cuota(movimiento, cuota, *, operacion_principal: bool = False) -> bool:
    """True si el movimiento registró cobro (total o parcial) imputado a esta cuota."""
    cuota_id = int(cuota.id)
    numero = int(cuota.numero_cuota)
    contrato_id = int(cuota.contrato_id)

    payload = payload_raiz_desde_movimiento_detalle(movimiento)
    if payload.get('pago_cuota_mensual') and int(payload.get('cuota_id') or 0) == cuota_id:
        return True

    cache_key = '_cache_lineas_imputables_op' if operacion_principal else '_cache_lineas_imputables'
    lineas = getattr(movimiento, cache_key, None)
    if lineas is None:
        lineas = lineas_imputables_desde_movimiento(movimiento, operacion_principal=operacion_principal)
        setattr(movimiento, cache_key, lineas)
    for it in lineas:
        raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
        if raw_qid.isdigit() and int(raw_qid) == cuota_id:
            return True

    concepto = getattr(movimiento, 'concepto', None) or ''
    if f'Contrato #{contrato_id} — Cuota {numero}/' in concepto:
        return True
    if f'Cuota {numero}/' in concepto and f'Contrato #{contrato_id}' in concepto:
        return True

    # Legacy: mes_alquiler_texto_recibo («junio / 2023») sin cuota_objetivo_id
    mes_txt = str(payload.get('mes_alquiler_texto_recibo') or '').strip().lower()
    fv = getattr(cuota, 'fecha_vencimiento', None)
    if mes_txt and fv is not None:
        nombre_mes = None
        for nombre, num in MESES_ES.items():
            if num == int(fv.month):
                nombre_mes = nombre
                break
        if nombre_mes and nombre_mes in mes_txt:
            m_anio = re.search(r'(20\d{2})', mes_txt)
            if not m_anio or int(m_anio.group(1)) == int(fv.year):
                if lineas or any(
                    linea_es_imputacion_alquiler_cuota(it)
                    for it in payload_conceptos_desde_movimiento_detalle(movimiento)
                ):
                    return True

    # Observaciones de línea: «A CUENTA AGOSTO 2026» / «SALDO JUNIO»
    if fv is not None:
        for it in payload_conceptos_desde_movimiento_detalle(movimiento):
            if not linea_es_imputacion_alquiler_cuota(it):
                continue
            mes_n, anio_n = mes_anio_desde_texto(texto_linea_concepto(it))
            if mes_n is None or int(mes_n) != int(fv.month):
                continue
            if anio_n is not None and int(anio_n) != int(fv.year):
                continue
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


def mover_credito_adelanto_entre_cuotas(contrato, desde_numero: int, hacia_numero: int) -> dict:
    """
    Mueve credito_aplicado (adelanto / pago a cuenta) de una cuota a otra.
    Útil cuando el cobro quedó imputado al mes equivocado (ej. mayo ↔ junio).
    """
    desde_n = int(desde_numero)
    hacia_n = int(hacia_numero)
    if desde_n == hacia_n:
        raise ValueError('Elegí dos cuotas distintas.')

    origen = contrato.cuotas.filter(numero_cuota=desde_n).first()
    destino = contrato.cuotas.filter(numero_cuota=hacia_n).first()
    if not origen or not destino:
        raise ValueError('No se encontraron las cuotas indicadas.')
    if origen.estado not in ('pendiente', 'vencida'):
        raise ValueError(
            f'La cuota {desde_n} está {origen.get_estado_display()}; solo se mueve adelanto de pendientes/vencidas.'
        )
    if destino.estado not in ('pendiente', 'vencida'):
        raise ValueError(
            f'La cuota {hacia_n} está {destino.get_estado_display()}; el destino debe estar pendiente o vencida.'
        )

    monto = Decimal(str(origen.credito_aplicado or 0))
    if monto <= Decimal('0.05'):
        raise ValueError(f'La cuota {desde_n} no tiene adelanto/crédito para mover.')

    origen_num = origen.credito_origen_numero_cuota
    origen.credito_aplicado = Decimal('0')
    origen.credito_origen_numero_cuota = None
    origen.save(update_fields=['credito_aplicado', 'credito_origen_numero_cuota'])

    dest_tot = Decimal(str(destino.monto_total or 0))
    dest_cred = Decimal(str(destino.credito_aplicado or 0))
    nuevo_cred = dest_cred + monto
    if dest_tot > 0 and nuevo_cred > dest_tot:
        # Excedente vuelve a quedar en origen (no perder plata).
        exceso = nuevo_cred - dest_tot
        nuevo_cred = dest_tot
        if exceso > Decimal('0.05'):
            origen.credito_aplicado = exceso
            origen.credito_origen_numero_cuota = origen_num
            origen.save(update_fields=['credito_aplicado', 'credito_origen_numero_cuota'])

    destino.credito_aplicado = nuevo_cred
    if origen_num is not None:
        destino.credito_origen_numero_cuota = origen_num
    elif destino.credito_origen_numero_cuota is None:
        destino.credito_origen_numero_cuota = desde_n
    destino.save(update_fields=['credito_aplicado', 'credito_origen_numero_cuota'])

    return {
        'desde': desde_n,
        'hacia': hacia_n,
        'monto': monto,
        'saldo_destino': destino.saldo_para_cobro(),
        'credito_destino': Decimal(str(destino.credito_aplicado or 0)),
        'credito_origen_restante': Decimal(str(origen.credito_aplicado or 0)),
    }


def marcar_cuota_pagada_desde_recibo_mes(
    contrato, movimiento, mes_nombre: str | None = None, anio: int | None = None
) -> dict:
    """
    Marca pagada la cuota del mes indicado (ej. «junio») usando el importe del movimiento.
    Para recibos legacy (concepto 1290) que no imputaron al plan.
    """
    import re

    from django.utils import timezone as tz

    hoy = tz.now().date()
    mov = movimiento
    if mov is None:
        raise ValueError('Falta el movimiento/recibo.')

    # Resolver mes desde argumento o desde JSON del movimiento
    mes_txt = (mes_nombre or '').strip().lower()
    anio_n = anio
    if not mes_txt:
        raw = (getattr(mov, 'concepto_detalle', None) or '').strip()
        if raw.startswith('{'):
            try:
                data = json.loads(raw)
                mes_txt = str(data.get('mes_alquiler_texto_recibo') or '').strip().lower()
            except (json.JSONDecodeError, TypeError, ValueError):
                mes_txt = ''
    meses_es = {
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
        'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
        'noviembre': 11, 'diciembre': 12,
    }
    mes_n = None
    for nombre, num in meses_es.items():
        if nombre in mes_txt:
            mes_n = num
            break
    if mes_n is None:
        raise ValueError(
            'No se pudo determinar el mes del recibo. Indicá el mes (ej. junio).'
        )
    if anio_n is None:
        m_anio = re.search(r'(20\d{2})', mes_txt)
        if m_anio:
            anio_n = int(m_anio.group(1))

    candidatas = list(
        contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).order_by('numero_cuota')
    )
    cuota = None
    for c in candidatas:
        if not c.fecha_vencimiento:
            continue
        if c.fecha_vencimiento.month != mes_n:
            continue
        if anio_n is not None and c.fecha_vencimiento.year != int(anio_n):
            continue
        cuota = c
        break
    if cuota is None:
        for c in candidatas:
            if c.fecha_vencimiento and c.fecha_vencimiento.month == mes_n:
                cuota = c
                break
    if cuota is None:
        raise ValueError(f'No hay cuota pendiente/vencida para el mes {mes_n}.')

    # Importe a imputar: líneas 1000/29/1290/1/15 o monto del movimiento
    lineas = lineas_imputables_desde_movimiento(mov)
    cubierto = sum((parse_decimal_monto(it.get('importe')) for it in lineas), Decimal('0'))
    if cubierto <= Decimal('0.05'):
        for it in payload_conceptos_desde_movimiento_detalle(mov):
            cid = _normalizar_codigo_concepto_caja(it.get('id') or it.get('codigo'))
            nom = (it.get('nombre') or '').lower()
            if cid in CODIGOS_IMPUTACION_ALQUILER_CUOTA or 'alquiler' in nom:
                cubierto += parse_decimal_monto(it.get('importe'))
    if cubierto <= Decimal('0.05'):
        cubierto = (
            Decimal(str(getattr(mov, 'monto_efectivo', None) or 0))
            + Decimal(str(getattr(mov, 'monto_cheque', None) or 0))
            + Decimal(str(getattr(mov, 'monto_tarjeta', None) or 0))
            + Decimal(str(getattr(mov, 'monto_deposito', None) or 0))
        )
    if cubierto <= Decimal('0.05'):
        raise ValueError('El recibo no tiene un importe de alquiler usable.')

    # Nunca bajar el monto_base al importe del recibo: un «pago a cuenta» de 525200
    # sobre una cuota de 568900 debe quedar como adelanto, no como mes pagado de 525200.
    resultado = imputar_importe_a_cuota(
        cuota, cubierto, mov, hoy, origen_numero_cuota=int(cuota.numero_cuota)
    )
    cuota.refresh_from_db()
    return {
        'cuota_numero': int(cuota.numero_cuota),
        'mes': mes_n,
        'anio': cuota.fecha_vencimiento.year if cuota.fecha_vencimiento else anio_n,
        'importe': cubierto,
        'resultado': resultado,
        'estado': cuota.estado,
    }


def dejar_cuota_en_adelanto_parcial(
    contrato,
    numero_cuota: int,
    monto_cuota: Decimal,
    credito_total: Decimal,
) -> dict:
    """
    Deja una cuota como adelanto parcial (pendiente/vencida con crédito).
    Útil cuando un pago a cuenta se marcó erróneamente como «Pagada».

    Ejemplo sept: monto 568900, crédito 23518+525200=548718 → saldo ~20182.
    """
    from django.utils import timezone as tz

    numero = int(numero_cuota)
    monto = Decimal(str(monto_cuota or 0))
    credito = Decimal(str(credito_total or 0))
    if monto <= Decimal('0.05'):
        raise ValueError('El monto de la cuota debe ser mayor a cero.')
    if credito < 0:
        raise ValueError('El crédito a favor no puede ser negativo.')

    cuota = contrato.cuotas.filter(numero_cuota=numero).first()
    if not cuota:
        raise ValueError(f'No existe la cuota {numero}.')

    hoy = tz.now().date()
    if cuota.fecha_vencimiento and cuota.fecha_vencimiento < hoy:
        estado = 'vencida'
    else:
        estado = 'pendiente'

    cuota.monto_base = monto
    cuota.recargo_mora = Decimal('0')
    cuota.descuento = Decimal('0')
    cuota.monto_total = monto
    cuota.credito_aplicado = credito
    cuota.estado = estado
    cuota.fecha_pago = None
    cuota.movimiento = None
    cuota.save(
        update_fields=[
            'monto_base',
            'monto_total',
            'recargo_mora',
            'descuento',
            'credito_aplicado',
            'estado',
            'fecha_pago',
            'movimiento',
        ]
    )
    cuota.refresh_from_db()
    return {
        'cuota_numero': numero,
        'monto': monto,
        'credito': credito,
        'saldo': cuota.saldo_para_cobro(),
        'estado': cuota.estado,
    }


def dejar_cuota_con_saldo_a_cobrar(contrato, numero_cuota: int, saldo_a_cobrar: Decimal) -> dict:
    """
    Deja la cuota pendiente/vencida con el saldo a cobrar indicado.
    El crédito se calcula como monto_cuota - saldo (usa el monto_base actual de la cuota).
    """
    numero = int(numero_cuota)
    saldo = Decimal(str(saldo_a_cobrar or 0))
    if saldo < 0:
        raise ValueError('El saldo a cobrar no puede ser negativo.')
    cuota = contrato.cuotas.filter(numero_cuota=numero).first()
    if not cuota:
        raise ValueError(f'No existe la cuota {numero}.')
    monto = Decimal(str(cuota.monto_total or cuota.monto_base or 0))
    if monto <= Decimal('0.05'):
        raise ValueError(f'La cuota {numero} no tiene monto definido.')
    if saldo > monto + Decimal('0.05'):
        raise ValueError(
            f'El saldo ${saldo} no puede ser mayor al monto de la cuota ${monto}.'
        )
    credito = monto - saldo
    return dejar_cuota_en_adelanto_parcial(contrato, numero, monto, credito)


def limpiar_mora_automatica_cuotas(contrato) -> int:
    """
    Quita recargo_mora de cuotas pendientes/vencidas y recalcula monto_total = monto_base.
    La mora al 1%/día se aplicaba sola al abrir Cobrar y dejaba saldos inventados.
    """
    n = 0
    for cuota in contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).iterator():
        mora = Decimal(str(cuota.recargo_mora or 0))
        if mora <= Decimal('0.005'):
            esperado = Decimal(str(cuota.monto_base or 0)) - Decimal(str(cuota.descuento or 0))
            if abs(Decimal(str(cuota.monto_total or 0)) - esperado) > Decimal('0.05'):
                cuota.monto_total = max(Decimal('0'), esperado)
                cuota.save(update_fields=['monto_total'])
                n += 1
            continue
        cuota.recargo_mora = Decimal('0')
        cuota.descuento = Decimal(str(cuota.descuento or 0))
        cuota.monto_total = max(
            Decimal('0'),
            Decimal(str(cuota.monto_base or 0)) - cuota.descuento,
        )
        cuota.save(update_fields=['recargo_mora', 'monto_total', 'descuento'])
        n += 1
    return n


def reimputar_desde_recibos_existentes(contrato, hoy=None) -> int:
    """
    Si hay movimientos con concepto 1000/29/1290 apuntando a una cuota pendiente/vencida
    por el saldo completo, marca esa cuota pagada (recibo existe, plan no actualizado).
    También intenta por mes_alquiler_texto_recibo (recibos legacy sin cuota_objetivo_id).

    No debe ejecutarse en cada GET del detalle: un pago a cuenta (parcial) ya cargado
    como crédito se reinterpretaba como cobro total y dejaba la cuota «Pagada» otra vez.
    """
    from django.utils import timezone as tz

    from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

    hoy = hoy or tz.now().date()
    tol = Decimal('0.05')
    movs = list(
        MovimientoCaja.objects.filter(
            concepto__icontains=f'Contrato #{contrato.id}',
            propiedad_id=contrato.propiedad_id,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            fecha_eliminacion__isnull=True,
        ).order_by('fecha', 'id')
    )
    if not movs:
        return 0
    n = 0
    for cuota in contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).order_by('numero_cuota'):
        # Si ya hay adelanto/crédito, no forzar «pagada» (evita deshacer correcciones).
        if Decimal(str(cuota.credito_aplicado or 0)) > tol:
            continue
        recibos = movimientos_recibo_por_cuota(cuota, movs)
        if not recibos:
            continue
        mov = recibos[-1]
        lineas = lineas_imputables_desde_movimiento(mov)
        cubierto = Decimal('0')
        for it in lineas:
            raw_qid = str(it.get('cuota_objetivo_id') or '').strip()
            if raw_qid.isdigit() and int(raw_qid) == int(cuota.id):
                cubierto += parse_decimal_monto(it.get('importe'))
        if cubierto <= tol:
            continue
        saldo = cuota.saldo_para_cobro()
        if saldo <= tol:
            continue
        # Pago parcial / a cuenta: no marcar pagada si no cubre el monto de la cuota.
        monto_cuota = Decimal(str(cuota.monto_total or cuota.monto_base or 0))
        if cubierto + tol < monto_cuota:
            continue
        try:
            if cubierto + tol >= saldo:
                marcar_cuota_pagada_con_excedente_a_favor(cuota, cubierto, mov, hoy)
                n += 1
        except ValueError:
            continue

    # Recibos legacy (1290) con mes en el JSON: solo si la cuota no tiene adelanto
    # y el importe del recibo cubre el monto completo del mes.
    for mov in movs:
        raw = (getattr(mov, 'concepto_detalle', None) or '').strip()
        if not raw.startswith('{'):
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        mes_txt = str(data.get('mes_alquiler_texto_recibo') or '').strip()
        if not mes_txt:
            continue
        # Estimar importe de alquiler del movimiento
        cubierto = Decimal('0')
        for it in list(data.get('conceptos') or []):
            cid = _normalizar_codigo_concepto_caja(it.get('id') or it.get('codigo'))
            nom = (it.get('nombre') or '').lower()
            if cid in CODIGOS_IMPUTACION_ALQUILER_CUOTA or 'alquiler' in nom:
                cubierto += parse_decimal_monto(it.get('importe'))
        if cubierto <= tol:
            continue
        try:
            meses_es = {
                'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
                'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10,
                'noviembre': 11, 'diciembre': 12,
            }
            mes_n = None
            mes_l = mes_txt.lower()
            for nombre, num in meses_es.items():
                if nombre in mes_l:
                    mes_n = num
                    break
            if mes_n is None:
                continue
            cuota = None
            for c in contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).order_by('numero_cuota'):
                if c.fecha_vencimiento and c.fecha_vencimiento.month == mes_n:
                    cuota = c
                    break
            if cuota is None:
                continue
            if Decimal(str(cuota.credito_aplicado or 0)) > tol:
                continue
            monto_cuota = Decimal(str(cuota.monto_total or cuota.monto_base or 0))
            if cubierto + tol < monto_cuota:
                # Pago a cuenta / parcial: no marcar pagada
                continue
            res = marcar_cuota_pagada_desde_recibo_mes(contrato, mov, mes_nombre=mes_txt)
            if res.get('estado') in ('pagada', 'pagada_con_mora'):
                n += 1
        except ValueError:
            continue
    return n


def mapa_movimientos_recibo_por_cuota_id(cuotas, movimientos_iterable) -> dict[int, list]:
    """cuota_id → movimientos/recibos que la imputan (una sola pasada)."""
    cuotas_list = list(cuotas)
    movs = list(movimientos_iterable)
    out: dict[int, list] = {int(c.id): [] for c in cuotas_list}
    vistos: dict[int, set[int]] = {int(c.id): set() for c in cuotas_list}

    for mov in movs:
        mid = int(mov.id)
        for c in cuotas_list:
            cid = int(c.id)
            if mid in vistos[cid]:
                continue
            if movimiento_imputa_cuota(mov, c):
                vistos[cid].add(mid)
                out[cid].append(mov)

    for c in cuotas_list:
        cid = int(c.id)
        if c.movimiento_id and int(c.movimiento_id) not in vistos[cid]:
            mov_final = getattr(c, 'movimiento', None)
            if mov_final is not None:
                out[cid].append(mov_final)

    for cid, lista in out.items():
        lista.sort(key=lambda m: (m.fecha, m.id))
    return out


def mapa_cuota_ids_por_movimiento(cuotas, movimientos_iterable) -> dict[int, list[int]]:
    """movimiento_id → cuotas imputadas por ese recibo (ordenadas por número de cuota)."""
    cuotas_list = list(cuotas)
    cuotas_by_id = {int(c.id): c for c in cuotas_list}
    out: dict[int, set[int]] = {}

    def _add(mid: int, cid: int) -> None:
        out.setdefault(int(mid), set()).add(int(cid))

    for mov in movimientos_iterable:
        mid = int(mov.id)
        for c in cuotas_list:
            if movimiento_imputa_cuota(mov, c):
                _add(mid, int(c.id))

    for c in cuotas_list:
        if c.movimiento_id:
            _add(int(c.movimiento_id), int(c.id))

    return {
        mid: sorted(ids, key=lambda cid: int(cuotas_by_id[cid].numero_cuota))
        for mid, ids in out.items()
    }


def movimiento_recibo_principal_cuota(cuota, movimientos_iterable=None) -> int | None:
    """ID del movimiento de caja que cobró esta cuota (recibo principal)."""
    recibos_attr = getattr(cuota, 'recibos_cobro', None)
    if recibos_attr:
        return int(recibos_attr[0].id)
    recibos = movimientos_recibo_por_cuota(cuota, movimientos_iterable or [])
    if recibos:
        return int(recibos[0].id)
    if cuota.movimiento_id:
        return int(cuota.movimiento_id)
    return None


def cuota_ids_mismo_recibo(
    cuota,
    cuotas_iterable,
    movimientos_iterable,
    *,
    solo_ids: set[int] | None = None,
    mapa_mov: dict | None = None,
) -> list[int]:
    """
    Cuotas del mismo recibo que la cuota dada.
    Si solo_ids está definido, limita a ese subconjunto (p. ej. liquidables).
    mapa_mov: cache opcional de mapa_cuota_ids_por_movimiento (evita rebuild O(n²)).
    """
    mid = movimiento_recibo_principal_cuota(cuota, movimientos_iterable)
    if mid is None:
        cid = int(cuota.id)
        return [cid] if solo_ids is None or cid in solo_ids else []

    mapa = mapa_mov if mapa_mov is not None else mapa_cuota_ids_por_movimiento(
        cuotas_iterable, movimientos_iterable
    )
    ids = mapa.get(mid, [int(cuota.id)])
    if solo_ids is not None:
        ids = [i for i in ids if i in solo_ids]
    return ids or ([int(cuota.id)] if int(cuota.id) in (solo_ids or {int(cuota.id)}) else [])


def movimientos_ingreso_contrato(contrato, *, limite: int = 300) -> list:
    """Ingresos de caja vinculados a este contrato (para agrupar cuotas por recibo)."""
    from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

    if not contrato or not getattr(contrato, 'propiedad_id', None):
        return []
    cid = int(contrato.id)
    # Filtrar en SQL (evita traer 300 ingresos ajenos y recorrerlos en Python)
    return list(
        MovimientoCaja.objects.filter(
            propiedad_id=contrato.propiedad_id,
            sucursal_id=contrato.sucursal_id,
            tipo=TipoMovimientoCajaEnum.INGRESO,
            fecha_eliminacion__isnull=True,
            concepto__icontains=f'Contrato #{cid}',
        )
        .select_related('recibo')
        .order_by('-fecha')[:limite]
    )
