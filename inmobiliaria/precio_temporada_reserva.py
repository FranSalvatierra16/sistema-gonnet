"""
Reglas de temporada para alquiler por día (tipo de precio según fecha).
Las vacaciones de invierno son configurables por sucursal (día/mes, se repiten cada año).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional, Tuple


@dataclass(frozen=True)
class RangoVacacionesInvierno:
    desde: Optional[date] = None
    hasta: Optional[date] = None


def rango_vacaciones_invierno_sucursal(sucursal) -> RangoVacacionesInvierno:
    if sucursal is None:
        return RangoVacacionesInvierno()
    return RangoVacacionesInvierno(
        getattr(sucursal, 'vacaciones_invierno_desde', None),
        getattr(sucursal, 'vacaciones_invierno_hasta', None),
    )


def _md(d: date) -> Tuple[int, int]:
    return (d.month, d.day)


def fecha_en_vacaciones_invierno(
    d: date,
    rango: Optional[RangoVacacionesInvierno] = None,
) -> bool:
    """
    True si el día cae en vacaciones de invierno.
    Sin rango configurado: todo julio (comportamiento histórico).
    """
    desde = rango.desde if rango else None
    hasta = rango.hasta if rango else None
    if not desde or not hasta:
        return d.month == 7
    d_md = _md(d)
    desde_md = _md(desde)
    hasta_md = _md(hasta)
    if desde_md <= hasta_md:
        return desde_md <= d_md <= hasta_md
    return d_md >= desde_md or d_md <= hasta_md


def dia_a_usar_para_noche(fecha_inicio: date, noche: int) -> date:
    """Día cuyo precio aplica a la noche (salida salvo Año Nuevo)."""
    from datetime import timedelta

    dia_salida = fecha_inicio + timedelta(noche)
    dia_llegada = fecha_inicio + timedelta(noche + 1)
    if (
        dia_salida.month == 12
        and dia_salida.day == 31
        and dia_llegada.month == 1
        and dia_llegada.day == 1
    ):
        return dia_llegada
    return dia_salida


def tipo_precio_para_dia_reserva(
    dia_a_usar: date,
    vacaciones_invierno: Optional[RangoVacacionesInvierno] = None,
) -> str:
    if dia_a_usar.month == 1:
        return 'QUINCENA_1_ENERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_ENERO'
    if dia_a_usar.month == 2:
        return 'QUINCENA_1_FEBRERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_FEBRERO'
    if dia_a_usar.month == 3:
        return 'QUINCENA_1_MARZO' if dia_a_usar.day <= 15 else 'QUINCENA_2_MARZO'
    if fecha_en_vacaciones_invierno(dia_a_usar, vacaciones_invierno):
        return 'VACACIONES_INVIERNO'
    if dia_a_usar.month == 12:
        return 'QUINCENA_1_DICIEMBRE' if dia_a_usar.day <= 15 else 'QUINCENA_2_DICIEMBRE'
    return 'TEMPORADA_BAJA'


def formatear_rango_vacaciones_invierno(rango: RangoVacacionesInvierno) -> str:
    if rango.desde and rango.hasta:
        return f'{rango.desde.strftime("%d/%m")} al {rango.hasta.strftime("%d/%m")} (cada año)'
    return 'Todo julio (predeterminado)'
