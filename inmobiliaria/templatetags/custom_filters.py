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
