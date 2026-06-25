"""Tipo de operación y nº de carpeta para liquidaciones y carátulas."""
from django.urls import reverse

from inmobiliaria.models.comision import clasificar_tipo_operacion_reserva

ETIQUETAS_TIPO_OPERACION = {
    'dia': 'Por día',
    'estudiante': 'Estudiante',
    'invierno': 'Invierno (9 meses)',
    '24': '24 meses',
    'otro': 'Otro contrato',
}


def _categoria_contrato(contrato):
    meses = int(getattr(contrato, 'duracion_meses', None) or 0)
    if meses == 9:
        return 'invierno'
    if meses == 24:
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


def info_operacion_liquidacion(liquidacion):
    """
    Devuelve tipo_key, tipo_display, numero_carpeta y si la operación usa carpeta (invierno / 24 meses).
    """
    from inmobiliaria.models import ContratoAlquiler, Reserva

    contrato = getattr(liquidacion, 'contrato', None)
    reserva = getattr(liquidacion, 'reserva', None)

    if contrato is not None:
        key = _categoria_contrato(contrato)
        carpeta = (getattr(contrato, 'numero_carpeta', None) or '').strip() or None
        return {
            'tipo_key': key,
            'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
            'numero_carpeta': carpeta,
            'muestra_carpeta': key in ('invierno', '24'),
            'operacion_ref': f'Contrato #{contrato.id}',
            'url_caratula': reverse('inmobiliaria:caratula_contrato', args=[contrato.id]),
        }

    if reserva is not None:
        key = _categoria_reserva(reserva)
        carpeta = (getattr(reserva, 'numero_carpeta', None) or '').strip() or None
        return {
            'tipo_key': key,
            'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
            'numero_carpeta': carpeta,
            'muestra_carpeta': key in ('invierno', '24'),
            'operacion_ref': f'Reserva #{reserva.id}',
            'url_caratula': reverse('inmobiliaria:caratula_reserva', args=[reserva.id]),
        }

    for op in liquidacion.operaciones_incluidas or []:
        if not isinstance(op, dict):
            continue
        tipo = (op.get('tipo') or '').strip().lower()
        try:
            pk = int(op['id'])
        except (KeyError, TypeError, ValueError):
            continue
        if tipo == 'contrato':
            c = ContratoAlquiler.objects.filter(pk=pk).first()
            if c:
                key = _categoria_contrato(c)
                carpeta = (c.numero_carpeta or '').strip() or None
                return {
                    'tipo_key': key,
                    'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
                    'numero_carpeta': carpeta,
                    'muestra_carpeta': key in ('invierno', '24'),
                    'operacion_ref': f'Contrato #{c.id}',
                    'url_caratula': reverse('inmobiliaria:caratula_contrato', args=[c.id]),
                }
        if tipo == 'reserva':
            r = Reserva.objects.filter(pk=pk).first()
            if r:
                key = _categoria_reserva(r)
                carpeta = (r.numero_carpeta or '').strip() or None
                return {
                    'tipo_key': key,
                    'tipo_display': ETIQUETAS_TIPO_OPERACION.get(key, key),
                    'numero_carpeta': carpeta,
                    'muestra_carpeta': key in ('invierno', '24'),
                    'operacion_ref': f'Reserva #{r.id}',
                    'url_caratula': reverse('inmobiliaria:caratula_reserva', args=[r.id]),
                }

    return {
        'tipo_key': '',
        'tipo_display': '—',
        'numero_carpeta': None,
        'muestra_carpeta': False,
        'operacion_ref': '—',
        'url_caratula': None,
    }
