import builtins

from django import template
from decimal import Decimal, InvalidOperation

from ..decimal_utils import format_monto_argentino, parse_decimal_monto

register = template.Library()
_abs = builtins.abs


@register.filter
def format_price(value, arg=None):
    """
    Formato argentino: miles con punto, decimales con coma (sin $).
    Por defecto 2 decimales (ej. 4.500.000,00). Enteros: {{ valor|format_price:0 }}
    """
    try:
        if arg is None or str(arg).strip() == '':
            dec_places = 2
        else:
            dec_places = max(0, min(10, int(arg)))
    except (TypeError, ValueError):
        dec_places = 2

    return format_monto_argentino(value, dec_places)

@register.filter
def format_importe_moneda(value, moneda='ARS'):
    """Importe con símbolo según moneda del contrato (ARS $ / USD U$S)."""
    formatted = format_monto_argentino(value, 2)
    if str(moneda or 'ARS').strip().upper() == 'USD':
        return f'U$S {formatted}'
    return f'${formatted}'

@register.filter
def abs(value):
    """Returns the absolute value of a number"""
    try:
        # Si ya es un Decimal, usarlo directamente
        if isinstance(value, Decimal):
            return _abs(value)
        # Si es un float o int, convertirlo a string primero
        if isinstance(value, (float, int)):
            return _abs(Decimal(str(value)))
        # Si es un string, intentar convertirlo
        if isinstance(value, str):
            return _abs(Decimal(value.replace(',', '.')))
        # Si no es ninguno de los tipos anteriores, devolver el valor original
        return value
    except (InvalidOperation, ValueError, TypeError):
        return value

@register.filter
def mul(value, arg):
    """Multiplies the value by the argument"""
    try:
        if isinstance(value, Decimal) and isinstance(arg, (int, float, Decimal)):
            return value * Decimal(str(arg))
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def sub(value, arg):
    """Subtracts the argument from the value"""
    try:
        if isinstance(value, Decimal) and isinstance(arg, (int, float, Decimal)):
            return value - Decimal(str(arg))
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter
def div(value, arg):
    """Divides the value by the argument"""
    try:
        if arg == 0:
            return 0
        if isinstance(value, Decimal) and isinstance(arg, (int, float, Decimal)):
            return value / Decimal(str(arg))
        return float(value) / float(arg)
    except (ValueError, TypeError, ZeroDivisionError):
        return 0

@register.filter
def get_caracteristicas(propiedad):
    """Genera una lista de características de la propiedad basada en sus campos booleanos"""
    caracteristicas = []
    
    if propiedad.amoblado:
        caracteristicas.append('Amoblado')
    if propiedad.cochera:
        caracteristicas.append('Cochera')
    if propiedad.tv_smart:
        caracteristicas.append('TV Smart')
    if propiedad.wifi:
        caracteristicas.append('WiFi')
    if propiedad.directv_prepago:
        caracteristicas.append('DirecTV prepago')
    if propiedad.ventilador:
        caracteristicas.append('Ventilador')
    if propiedad.aire:
        caracteristicas.append('Aire acondicionado')
    if propiedad.cable:
        caracteristicas.append('Cable')
    if propiedad.dependencia:
        caracteristicas.append('Dependencia')
    if propiedad.patio:
        caracteristicas.append('Patio')
    if propiedad.parrilla:
        caracteristicas.append('Parrilla')
    if propiedad.piscina:
        caracteristicas.append('Piscina')
    if propiedad.reciclado:
        caracteristicas.append('Reciclado')
    if propiedad.a_estrenar:
        caracteristicas.append('A estrenar')
    if propiedad.terraza:
        caracteristicas.append('Terraza')
    if propiedad.balcon:
        caracteristicas.append('Balcón')
    if propiedad.baulera:
        caracteristicas.append('Baulera')
    if propiedad.lavadero:
        caracteristicas.append('Lavadero')
    if propiedad.seguridad:
        caracteristicas.append('Seguridad')
    if propiedad.vista_al_Mar:
        caracteristicas.append('Vista al Mar')
    if propiedad.vista_panoramica:
        caracteristicas.append('Vista Panorámica')
    if propiedad.apto_credito:
        caracteristicas.append('Apto Crédito')
    
    if not caracteristicas:
        return 'Sin características especiales'
    
    return ', '.join(caracteristicas)

@register.filter
def get_item(dictionary, key):
    """Obtiene un elemento de un diccionario usando una clave"""
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


def formato_apellido_nombre(persona):
    """Apellido primero, luego nombre (recibos y comprobantes)."""
    if persona is None:
        return ''
    if isinstance(persona, dict):
        return formato_apellido_nombre_desde(
            persona.get('nombre'),
            persona.get('apellido'),
        )
    fn = getattr(persona, 'nombre_completo_display', None)
    if callable(fn):
        return fn() or ''
    return formato_apellido_nombre_desde(
        getattr(persona, 'nombre', None),
        getattr(persona, 'apellido', None),
    )


def formato_apellido_nombre_desde(nombre, apellido):
    """Apellido, Nombre a partir de campos sueltos."""
    ap = str(apellido or '').strip()
    nom = str(nombre or '').strip()
    if ap and nom:
        return f'{ap}, {nom}'
    return ap or nom or ''


@register.filter(name='apellido_nombre')
def apellido_nombre_filter(persona):
    return formato_apellido_nombre(persona)


@register.filter
def numero_recibo_display(recibo):
    """Número de recibo: modelo Recibo, numero_liquidacion del movimiento o fallback M-000123."""
    if not recibo:
        return ''
    n = (getattr(recibo, 'numero_recibo', None) or '').strip()
    if n:
        return n
    mov = getattr(recibo, 'movimiento_caja', None)
    if mov:
        from inmobiliaria.views import _numero_recibo_mostrar_movimiento

        return _numero_recibo_mostrar_movimiento(mov)
    return ''


@register.filter
def numero_recibo_movimiento(movimiento):
    """Número de recibo asociado a un movimiento de caja."""
    if not movimiento:
        return ''
    from inmobiliaria.views import _numero_recibo_mostrar_movimiento

    return _numero_recibo_mostrar_movimiento(movimiento)


@register.simple_tag(takes_context=True)
def url_recibo_movimiento(context, movimiento):
    """Enlace al recibo imprimible (contrato 24m, reserva por día o caja)."""
    if not movimiento:
        return '#'
    # Preferir URL precargada en lote (listados) para evitar N+1.
    precargada = getattr(movimiento, 'url_recibo', None)
    if precargada:
        return precargada
    cache_map = context.get('url_recibo_map') or {}
    mid = getattr(movimiento, 'id', None)
    if mid is not None and mid in cache_map:
        return cache_map[mid]
    request = context.get('request')
    sucursal = getattr(movimiento, 'sucursal', None)
    if sucursal is None and request and getattr(request, 'user', None):
        sucursal = getattr(request.user, 'sucursal', None)
    next_url = request.get_full_path() if request and hasattr(request, 'get_full_path') else None
    from inmobiliaria.views import _url_recibo_para_movimiento

    return _url_recibo_para_movimiento(movimiento, sucursal, next_url=next_url)
