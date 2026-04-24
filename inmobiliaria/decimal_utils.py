"""
Parseo de montos ingresados en formularios.

- Formato argentino: miles con punto y coma decimal (1.234.567,89).
- Sin coma: un solo punto con hasta 2 decimales se interpreta como decimal
  tipo US/Excel (350080.20); en caso contrario los puntos son separadores de miles.
"""

from __future__ import annotations

import builtins
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_abs = builtins.abs


def parse_decimal_monto(value) -> Decimal:
    """Convierte texto (o tipos numéricos) a Decimal para montos de formularios."""
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))

    t = str(value).strip()
    if not t:
        return Decimal("0")

    neg = False
    if t.startswith("-"):
        neg = True
        t = t[1:].strip()
    t = re.sub(r"[^\d.,]", "", t)
    if not t or t in {",", ".", "-"}:
        return Decimal("0")

    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        if t.count(".") == 1 and len(t.split(".")[-1]) <= 2:
            pass
        else:
            t = t.replace(".", "")

    if neg:
        t = "-" + t
    try:
        return Decimal(t)
    except InvalidOperation:
        return Decimal("0")


def _entero_miles_puntos(n: int) -> str:
    n = _abs(int(n))
    s = str(n)
    parts = []
    while len(s) > 3:
        parts.insert(0, s[-3:])
        s = s[:-3]
    if s:
        parts.insert(0, s)
    return ".".join(parts) if parts else "0"


def format_monto_argentino(value, dec_places: int = 2) -> str:
    """
    Formato argentino: miles con punto, decimales con coma (sin símbolo $).
    dec_places=0 solo muestra la parte entera con separador de miles.
    """
    try:
        dec_places = max(0, min(10, int(dec_places)))
    except (TypeError, ValueError):
        dec_places = 2

    try:
        if isinstance(value, Decimal):
            d = value
        elif isinstance(value, bool):
            d = Decimal(int(value))
        elif isinstance(value, int):
            d = Decimal(value)
        elif isinstance(value, float):
            d = Decimal(str(value))
        elif value is None or value == "":
            d = Decimal("0")
        else:
            d = parse_decimal_monto(value)
    except (InvalidOperation, ValueError, TypeError):
        return "0" if dec_places == 0 else ("0," + ("0" * dec_places))

    neg = d < 0
    d = _abs(d)

    if dec_places == 0:
        q = d.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        body = _entero_miles_puntos(int(q))
    else:
        exp = Decimal(10) ** -dec_places
        q = d.quantize(exp, rounding=ROUND_HALF_UP)
        s = format(q, "f")
        if "." in s:
            ip_str, fp_str = s.split(".", 1)
        else:
            ip_str, fp_str = s, ""
        fp_str = (fp_str + "0" * dec_places)[:dec_places]
        intpart = int(ip_str) if ip_str else 0
        body = f"{_entero_miles_puntos(intpart)},{fp_str}"

    return ("-" if neg else "") + body
