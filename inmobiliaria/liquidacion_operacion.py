"""Tipo de operación y nº de carpeta para liquidaciones y carátulas."""
from decimal import Decimal

from django.urls import reverse

MONEDA_ARS = 'ARS'
MONEDA_USD = 'USD'
_TOLERANCIA_LIQ = Decimal('0.05')


def normalizar_moneda(val):
    m = str(val or MONEDA_ARS).strip().upper()
    return MONEDA_USD if m == MONEDA_USD else MONEDA_ARS


def simbolo_moneda(moneda):
    return 'U$S' if normalizar_moneda(moneda) == MONEDA_USD else '$'


ETIQUETAS_TIPO_OPERACION = {
    'dia': 'Por día',
    'estudiante': 'Estudiante',
    'invierno': 'Invierno',
    '24': '24 meses',
    '6': '6 meses',
    'otro': 'Otro contrato',
}

TITULO_LIQUIDACION_POR_TIPO = {
    'dia': 'POR DÍA',
    'estudiante': 'ESTUDIANTE',
    'invierno': 'INVIERNO',
    '24': '24 MESES',
    '6': '6 MESES',
    'otro': 'COBRANZAS',
}


def _categoria_contrato(contrato):
    if hasattr(contrato, 'categoria_tipo_operacion'):
        return contrato.categoria_tipo_operacion()
    meses = int(getattr(contrato, 'duracion_meses', None) or 0)
    if meses == 9:
        return 'invierno'
    if meses >= 9:
        return '24'
    return 'otro'


def _categoria_reserva(reserva):
    """Reservas = alquiler por día (o estudiante); invierno/24 meses solo en contratos."""
    prop = getattr(reserva, 'propiedad', None)
    if prop and getattr(prop, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'estudiante'
    return 'dia'


def _numero_carpeta_contrato(contrato):
    if not contrato:
        return None
    raw = (getattr(contrato, 'numero_carpeta', None) or '').strip()
    if not raw or raw == '0':
        return None
    return raw


def contrato_desde_liquidacion(liquidacion):
    """Contrato vinculado: FK directo, operación principal o cuotas en operaciones_incluidas."""
    from inmobiliaria.models import ContratoAlquiler, CuotaMensual

    if getattr(liquidacion, 'contrato_id', None) and liquidacion.contrato_id:
        return liquidacion.contrato

    cuota_ids = []
    contrato_ids = []
    for op in liquidacion.operaciones_incluidas or []:
        if not isinstance(op, dict) or op.get('tipo') == 'division':
            continue
        tipo = (op.get('tipo') or '').strip().lower()
        try:
            pk = int(op['id'])
        except (KeyError, TypeError, ValueError):
            pk = None
        if tipo == 'contrato_operacion_principal' and pk:
            contrato_ids.append(pk)
        elif tipo == 'contrato' and pk:
            contrato_ids.append(pk)
            for cid in op.get('cuotas_ids') or []:
                try:
                    cuota_ids.append(int(cid))
                except (TypeError, ValueError):
                    pass
        elif tipo == 'contrato_cuota' and pk:
            cuota_ids.append(pk)
            for cid in op.get('cuotas_ids') or op.get('cuota_ids') or []:
                try:
                    cuota_ids.append(int(cid))
                except (TypeError, ValueError):
                    pass

    if len(contrato_ids) == 1:
        return ContratoAlquiler.objects.filter(pk=contrato_ids[0]).first()

    if not cuota_ids:
        return None

    cq = (
        CuotaMensual.objects.filter(id__in=cuota_ids)
        .select_related('contrato')
        .order_by('fecha_vencimiento')
        .first()
    )
    return cq.contrato if cq else None


def moneda_liquidacion(liquidacion):
    """Moneda efectiva de una liquidación (campo propio o contrato vinculado)."""
    if liquidacion and getattr(liquidacion, 'moneda', None):
        return normalizar_moneda(liquidacion.moneda)
    contrato = contrato_desde_liquidacion(liquidacion)
    if contrato:
        return normalizar_moneda(getattr(contrato, 'moneda', MONEDA_ARS))
    return MONEDA_ARS


def reserva_desde_liquidacion(liquidacion):
    from inmobiliaria.models import Reserva

    if getattr(liquidacion, 'reserva_id', None) and liquidacion.reserva_id:
        return liquidacion.reserva

    for op in liquidacion.operaciones_incluidas or []:
        if not isinstance(op, dict) or op.get('tipo') == 'division':
            continue
        if (op.get('tipo') or '').strip().lower() != 'reserva':
            continue
        try:
            pk = int(op['id'])
        except (KeyError, TypeError, ValueError):
            continue
        r = Reserva.objects.filter(pk=pk).first()
        if r:
            return r
    return None


def liquidaciones_activas_reserva(reserva):
    """Liquidaciones no canceladas de una reserva (FK o operaciones_incluidas)."""
    from inmobiliaria.models import LiquidacionPropietario

    if not reserva:
        return []
    rid = int(reserva.pk)
    candidatas = list(
        LiquidacionPropietario.objects.filter(reserva_id=rid)
        .exclude(estado='cancelada')
        .order_by('id')
    )
    vistos = {liq.pk for liq in candidatas}
    qs_extra = (
        LiquidacionPropietario.objects.filter(propiedad_id=reserva.propiedad_id)
        .exclude(estado='cancelada')
        .exclude(pk__in=vistos)
        .only(
            'id',
            'operaciones_incluidas',
            'monto_propietario',
            'monto_inmobiliaria',
            'monto_cochera',
            'monto_fondo_mantenimiento',
            'monto_a_pagar',
            'estado',
            'fecha_creacion',
        )
        .order_by('id')
    )
    for liq in qs_extra:
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            if (op.get('tipo') or '').lower() != 'reserva':
                continue
            try:
                if int(op.get('id')) == rid:
                    candidatas.append(liq)
                    break
            except (TypeError, ValueError):
                continue
    candidatas.sort(key=lambda x: (x.id or 0))
    return candidatas


def _montos_asignados_en_liquidaciones(liquidaciones):
    """Suma de prop/inm/cochera/fondo cargados en liquidaciones activas."""
    prop = inm = coch = fondo = Decimal('0')
    for liq in liquidaciones or []:
        prop += Decimal(str(getattr(liq, 'monto_propietario', None) or 0))
        inm += Decimal(str(getattr(liq, 'monto_inmobiliaria', None) or 0))
        coch += Decimal(str(getattr(liq, 'monto_cochera', None) or 0))
        fondo += Decimal(str(getattr(liq, 'monto_fondo_mantenimiento', None) or 0))
    return (
        prop.quantize(Decimal('0.01')),
        inm.quantize(Decimal('0.01')),
        coch.quantize(Decimal('0.01')),
        fondo.quantize(Decimal('0.01')),
    )


def _reparto_asignado_en_liquidaciones(reserva, liquidaciones):
    """
    Armado de cuadrados a partir de lo cargado en liquidaciones.

    Retorna (total, prop, inm, coch, fondo) o None si no hay montos útiles.

    - Si la suma cierra el total de la operación → esos valores.
    - Si ya asignaron oficina/cochera/fondo y el propietario va parcial,
      propietario del cuadro = total − oficina (lo que le corresponde en el reparto).
    - Si solo hay monto al propietario (sin oficina), se muestran esos montos
      tal cual (el saldo pendiente sigue calculándose aparte).
    """
    if not liquidaciones:
        return None
    total_op = Decimal(str(getattr(reserva, 'precio_total', None) or 0)).quantize(Decimal('0.01'))
    prop_a, inm_a, coch_a, fondo_a = _montos_asignados_en_liquidaciones(liquidaciones)
    if prop_a <= 0 and inm_a <= 0 and coch_a <= 0 and fondo_a <= 0:
        return None

    oficina = (inm_a + coch_a + fondo_a).quantize(Decimal('0.01'))
    suma = (prop_a + oficina).quantize(Decimal('0.01'))

    if total_op <= 0:
        return Decimal('0.00'), prop_a, inm_a, coch_a, fondo_a

    if abs(suma - total_op) <= _TOLERANCIA_LIQ:
        return total_op, prop_a, inm_a, coch_a, fondo_a

    if oficina > 0 and oficina < total_op:
        prop_full = (total_op - oficina).quantize(Decimal('0.01'))
        return total_op, prop_full, inm_a, coch_a, fondo_a

    return total_op, prop_a, inm_a, coch_a, fondo_a


def monto_propietario_corresponde_reserva(reserva) -> Decimal:
    """
    Monto total al propietario por la operación.

    Prioridad:
    1) Liquidaciones que cierran el total, o con oficina ya asignada
       (propietario = total − oficina).
    2) Overrides de carátula + precio por día (toma) / paquete.
    """
    from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

    if not reserva or not reserva.precio_total:
        return Decimal('0.00')

    total_op = Decimal(str(reserva.precio_total or 0)).quantize(Decimal('0.01'))
    liqs = liquidaciones_activas_reserva(reserva)
    if liqs and total_op > 0:
        prop_a, inm_a, coch_a, fondo_a = _montos_asignados_en_liquidaciones(liqs)
        oficina = (inm_a + coch_a + fondo_a).quantize(Decimal('0.01'))
        suma = (prop_a + oficina).quantize(Decimal('0.01'))
        if abs(suma - total_op) <= _TOLERANCIA_LIQ:
            return prop_a
        if oficina > 0 and oficina < total_op:
            return (total_op - oficina).quantize(Decimal('0.01'))

    total, prop, inm, _hay_toma = reparto_liquidacion_reserva_por_dia(reserva)
    _t, prop, _i, _c, _f = reserva.montos_liquidacion_efectivos(total, prop, inm)
    return Decimal(str(prop or 0)).quantize(Decimal('0.01'))


def montos_reparto_reserva_para_caratula(reserva):
    """
    Cuadrados de la carátula: total / propietario / inmobiliaria / cochera / fondo.

    Si ya liquidaron, usa los montos de esas liquidaciones (lo que cargaron al
    dividir propietario / oficina / cochera / fondo). Si no, toma + overrides.
    """
    from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

    if not reserva or not reserva.precio_total:
        z = Decimal('0.00')
        return z, z, z, z, z

    liqs = liquidaciones_activas_reserva(reserva)
    if liqs:
        desde_liq = _reparto_asignado_en_liquidaciones(reserva, liqs)
        if desde_liq is not None:
            return desde_liq

    total, prop, inm, _hay = reparto_liquidacion_reserva_por_dia(reserva)
    return reserva.montos_liquidacion_efectivos(total, prop, inm)


def monto_propietario_ya_liquidado_reserva(reserva, liquidaciones=None) -> Decimal:
    """Suma de monto_propietario de liquidaciones activas de la reserva."""
    liqs = liquidaciones if liquidaciones is not None else liquidaciones_activas_reserva(reserva)
    total = Decimal('0')
    for liq in liqs:
        total += Decimal(str(getattr(liq, 'monto_propietario', None) or 0))
    return total.quantize(Decimal('0.01'))


def saldo_liquidacion_reserva(reserva, liquidaciones=None) -> dict:
    """
    Estado de liquidación parcial de una reserva.
    corresponde = total al propietario; liquidado = suma de liquidaciones; pendiente = resto.
    """
    liqs = liquidaciones if liquidaciones is not None else liquidaciones_activas_reserva(reserva)
    corresponde = monto_propietario_corresponde_reserva(reserva)
    liquidado = monto_propietario_ya_liquidado_reserva(reserva, liqs)
    pendiente = (corresponde - liquidado).quantize(Decimal('0.01'))
    if pendiente < 0:
        pendiente = Decimal('0.00')
    completa = corresponde > 0 and pendiente <= _TOLERANCIA_LIQ
    return {
        'corresponde': corresponde,
        'liquidado': liquidado,
        'pendiente': pendiente,
        'completa': completa,
        'tiene_liquidaciones': bool(liqs),
        'liquidaciones': liqs,
        'cantidad': len(liqs),
    }


def _parse_fecha_parte_liq(valor):
    if not valor:
        return None
    if hasattr(valor, 'year') and hasattr(valor, 'month') and hasattr(valor, 'day'):
        return valor
    try:
        from datetime import datetime

        return datetime.strptime(str(valor)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _fecha_hasta_parte_creada_liquidacion(liq):
    """Fecha hasta de la parte liquidada en esta liquidación (división o campos de la liq.)."""
    for op in liq.operaciones_incluidas or []:
        if not isinstance(op, dict) or (op.get('tipo') or '').lower() != 'division':
            continue
        partes = op.get('operaciones') or []
        parte_n = op.get('parte_creada')
        elegida = None
        for p in partes:
            if isinstance(p, dict) and p.get('creada_en_esta_liquidacion'):
                elegida = p
                break
        if elegida is None and parte_n is not None:
            try:
                n = int(parte_n)
            except (TypeError, ValueError):
                n = None
            if n is not None:
                for p in partes:
                    if isinstance(p, dict) and int(p.get('numero') or 0) == n:
                        elegida = p
                        break
        if elegida:
            return _parse_fecha_parte_liq(elegida.get('fecha_hasta'))
    return getattr(liq, 'fecha_hasta', None)


def fechas_periodo_pendiente_reserva(reserva):
    """
    Rango de fechas que queda por liquidar.
    Si ya hubo partes, el "desde" es el "hasta" de la última parte liquidada
    (ej. liquidó 18→25 → pendiente 25→fin).
    """
    inicio = getattr(reserva, 'fecha_inicio', None)
    fin = getattr(reserva, 'fecha_fin', None)
    saldo = saldo_liquidacion_reserva(reserva)
    if not saldo['tiene_liquidaciones'] or saldo['completa']:
        return inicio, fin

    max_hasta = None
    for liq in saldo['liquidaciones']:
        fh = _fecha_hasta_parte_creada_liquidacion(liq)
        if fh and (max_hasta is None or fh > max_hasta):
            max_hasta = fh

    desde = max_hasta if max_hasta else inicio
    hasta = fin
    if desde and hasta and desde > hasta:
        desde = hasta
    return desde, hasta


def encadenar_fechas_partes_division(partes):
    """
    Las partes pendientes (monto 0) arrancan en el "hasta" de la parte anterior.
    Mutates and returns the list of dicts.
    """
    if not partes:
        return partes
    for i in range(len(partes) - 1):
        actual = partes[i]
        siguiente = partes[i + 1]
        if not isinstance(actual, dict) or not isinstance(siguiente, dict):
            continue
        try:
            monto_sig = Decimal(str(siguiente.get('monto') or '0').replace(',', '.'))
        except Exception:
            monto_sig = Decimal('0')
        pendiente = bool(siguiente.get('pendiente')) or monto_sig <= 0
        if pendiente and actual.get('fecha_hasta'):
            siguiente['fecha_desde'] = actual['fecha_hasta']
    return partes


def reserva_ids_completamente_liquidadas(propiedad) -> set:
    """
    IDs de reserva cuya parte al propietario ya está cubierta al 100%
    (una o más liquidaciones no canceladas). Las parciales NO entran.
    """
    from inmobiliaria.models import LiquidacionPropietario, Reserva

    if not propiedad:
        return set()
    candidatos = set()
    for liq in (
        LiquidacionPropietario.objects.filter(propiedad=propiedad)
        .exclude(estado='cancelada')
        .only('reserva_id', 'operaciones_incluidas')
    ):
        if liq.reserva_id:
            candidatos.add(int(liq.reserva_id))
        for op in liq.operaciones_incluidas or []:
            if not isinstance(op, dict):
                continue
            if (op.get('tipo') or '').lower() != 'reserva':
                continue
            try:
                candidatos.add(int(op['id']))
            except (KeyError, TypeError, ValueError):
                pass
    if not candidatos:
        return set()
    completas = set()
    for reserva in Reserva.objects.filter(id__in=candidatos, propiedad=propiedad).select_related(
        'propiedad'
    ):
        if saldo_liquidacion_reserva(reserva)['completa']:
            completas.add(int(reserva.id))
    return completas


def confirmar_caratula_por_liquidacion(liquidacion) -> list:
    """
    Al liquidar al propietario: marca la/s carátula/s como confirmada y acredita
    comisiones con fecha vencida. Evita volver a la carátula solo para confirmar.
    """
    if not liquidacion or getattr(liquidacion, 'estado', None) == 'cancelada':
        return []

    from inmobiliaria.models import Reserva
    from inmobiliaria.models.comision import (
        _reserva_ids_desde_liquidacion,
        acreditar_comisiones_operacion_por_caratula,
    )

    confirmadas = []

    for rid in _reserva_ids_desde_liquidacion(liquidacion):
        reserva = Reserva.objects.filter(pk=rid).first()
        if not reserva:
            continue
        if getattr(reserva, 'eliminada', False) or getattr(reserva, 'estado', None) == 'cancelada':
            continue
        if (getattr(reserva, 'estado_confirmacion_caratula', None) or 'pendiente') == 'confirmada':
            acreditar_comisiones_operacion_por_caratula(reserva=reserva)
            continue
        reserva.estado_confirmacion_caratula = 'confirmada'
        reserva.save(update_fields=['estado_confirmacion_caratula'])
        acreditar_comisiones_operacion_por_caratula(reserva=reserva)
        confirmadas.append(f'reserva #{rid}')

    contrato = None
    if getattr(liquidacion, 'contrato_id', None):
        contrato = liquidacion.contrato
    if contrato is None:
        contrato = contrato_desde_liquidacion(liquidacion)
    if contrato is not None and getattr(contrato, 'estado', None) != 'rescindido':
        if (getattr(contrato, 'estado_confirmacion_caratula', None) or 'pendiente') != 'confirmada':
            contrato.estado_confirmacion_caratula = 'confirmada'
            contrato.save(update_fields=['estado_confirmacion_caratula'])
            acreditar_comisiones_operacion_por_caratula(contrato=contrato)
            confirmadas.append(f'contrato #{contrato.pk}')
        else:
            acreditar_comisiones_operacion_por_caratula(contrato=contrato)

    return confirmadas


def titulo_tipo_liquidacion_cobranzas(info_op):
    key = (info_op or {}).get('tipo_key') or ''
    if key in TITULO_LIQUIDACION_POR_TIPO:
        return TITULO_LIQUIDACION_POR_TIPO[key]
    display = (info_op or {}).get('tipo_display') or 'COBRANZAS'
    return str(display).upper()


def info_operacion_liquidacion(liquidacion):
    """
    Devuelve tipo_key, tipo_display, numero_carpeta y si la operación usa carpeta (invierno / 24 meses).
    """
    reserva = reserva_desde_liquidacion(liquidacion)
    if reserva is not None:
        key = _categoria_reserva(reserva)
        return {
            'tipo_key': key,
            'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
            'numero_carpeta': None,
            'muestra_carpeta': False,
            'operacion_ref': f'Reserva #{reserva.id}',
            'url_caratula': reverse('inmobiliaria:caratula_reserva', args=[reserva.id]),
        }

    contrato = contrato_desde_liquidacion(liquidacion)
    if contrato is not None:
        key = _categoria_contrato(contrato)
        carpeta = _numero_carpeta_contrato(contrato)
        return {
            'tipo_key': key,
            'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
            'numero_carpeta': carpeta,
            'muestra_carpeta': key in ('invierno', '24'),
            'operacion_ref': f'Contrato #{contrato.id}',
            'url_caratula': reverse('inmobiliaria:caratula_contrato', args=[contrato.id]),
        }

    return {
        'tipo_key': '',
        'tipo_display': '—',
        'numero_carpeta': None,
        'muestra_carpeta': False,
        'operacion_ref': '—',
        'url_caratula': None,
    }
