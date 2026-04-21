import builtins

from django import template
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

register = template.Library()
_abs = builtins.abs


def _parse_decimal(value):
    """Convierte valor de plantilla a Decimal (acepta AR con puntos miles y coma decimal)."""
    if value is None or value == '':
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        t = value.strip()
        if not t:
            return Decimal('0')
        # 1.234.567,89 → quitar puntos de miles, coma a punto decimal
        if ',' in t:
            t = t.replace('.', '').replace(',', '.')
        else:
            # Solo puntos: puede ser miles (1.000) o decimal US (1.5)
            if t.count('.') == 1 and len(t.split('.')[-1]) <= 2:
                pass  # decimal corto
            else:
                t = t.replace('.', '')
        return Decimal(t)
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def _entero_miles_puntos(n: int) -> str:
    n = _abs(int(n))
    s = str(n)
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    if s:
        parts.insert(0, s)
    return '.'.join(parts) if parts else '0'


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

    try:
        d = _parse_decimal(value)
    except (InvalidOperation, ValueError, TypeError):
        return '0' if dec_places == 0 else ('0,' + ('0' * dec_places))

    neg = d < 0
    d = _abs(d)

    if dec_places == 0:
        q = d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        body = _entero_miles_puntos(int(q))
    else:
        exp = Decimal(10) ** -dec_places
        q = d.quantize(exp, rounding=ROUND_HALF_UP)
        s = format(q, 'f')
        if '.' in s:
            ip_str, fp_str = s.split('.', 1)
        else:
            ip_str, fp_str = s, ''
        fp_str = (fp_str + '0' * dec_places)[:dec_places]
        intpart = int(ip_str) if ip_str else 0
        body = f'{_entero_miles_puntos(intpart)},{fp_str}'

    return ('-' if neg else '') + body

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
