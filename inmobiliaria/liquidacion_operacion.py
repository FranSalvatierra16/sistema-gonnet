"""Tipo de operación y nº de carpeta para liquidaciones y carátulas."""
from django.urls import reverse

from inmobiliaria.models.comision import clasificar_tipo_operacion_reserva

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
    prop = getattr(reserva, 'propiedad', None)
    if prop and getattr(prop, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'estudiante'
    cat = clasificar_tipo_operacion_reserva(reserva)
    if cat == 'invierno':
        return 'invierno'
    if cat == '24':
        return '24'
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
