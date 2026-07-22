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
        .only('id', 'operaciones_incluidas', 'monto_propietario', 'monto_a_pagar', 'estado', 'fecha_creacion')
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


def monto_propietario_corresponde_reserva(reserva) -> Decimal:
    """Monto total que corresponde al propietario por la operación (con overrides de carátula)."""
    from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

    if not reserva or not reserva.precio_total:
        return Decimal('0.00')
    total, prop, inm, _hay_toma = reparto_liquidacion_reserva_por_dia(reserva)
    _t, prop, _i, _c, _f = reserva.montos_liquidacion_efectivos(total, prop, inm)
    return Decimal(str(prop or 0)).quantize(Decimal('0.01'))


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
