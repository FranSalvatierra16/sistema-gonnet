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
