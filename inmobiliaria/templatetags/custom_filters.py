from django import template
from decimal import Decimal, InvalidOperation

register = template.Library()

@register.filter
def format_price(value):
    try:
        return "{:,.0f}".format(value).replace(',', '.')
    except (ValueError, TypeError):
        return value

@register.filter
def abs(value):
    """Returns the absolute value of a number"""
    try:
        # Si ya es un Decimal, usarlo directamente
        if isinstance(value, Decimal):
            return abs(value)
        # Si es un float o int, convertirlo a string primero
        if isinstance(value, (float, int)):
            return abs(Decimal(str(value)))
        # Si es un string, intentar convertirlo
        if isinstance(value, str):
            return abs(Decimal(value.replace(',', '.')))
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
