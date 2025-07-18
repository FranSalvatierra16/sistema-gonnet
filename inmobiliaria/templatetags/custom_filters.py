from django import template
from decimal import Decimal

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
        return abs(Decimal(str(value)))
    except (TypeError, ValueError):
        return value
