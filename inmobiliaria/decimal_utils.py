"""
Parseo de montos ingresados en formularios.

- Formato argentino: miles con punto y coma decimal (1.234.567,89).
- Sin coma: un solo punto con hasta 2 decimales se interpreta como decimal
  tipo US/Excel (350080.20); en caso contrario los puntos son separadores de miles.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


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
