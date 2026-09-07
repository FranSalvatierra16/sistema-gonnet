"""Liquidación mensual de productores: sueldo básico + comisiones."""
from decimal import Decimal

from inmobiliaria.models import Vendedor
from inmobiliaria.oficina_resumen import MESES_ES, _rango_mes, _totales_comisiones_vendedor


def total_a_pagar_productor(sueldo_basico, comisiones, no_suma_si_superan):
    """
    Regla de liquidación:
    - Flag OFF → comisiones + básico
    - Flag ON y comisiones >= básico (>0) → solo comisiones (no suma el básico)
    - Flag ON y comisiones < básico → comisiones + básico
    """
    basico = Decimal(str(sueldo_basico or 0)).quantize(Decimal('0.01'))
    comis = Decimal(str(comisiones or 0)).quantize(Decimal('0.01'))
    basico_aplicado = True
    if no_suma_si_superan and basico > 0 and comis >= basico:
        total = comis
        basico_aplicado = False
    else:
        total = (comis + basico).quantize(Decimal('0.01'))
    return total, basico_aplicado


def construir_liquidacion_productores(sucursal, anio, mes):
    """
    Filas por vendedor activo de la sucursal para el mes:
    comisiones, básico, si se sumó el básico, total a pagar.
    """
    fecha_desde, fecha_hasta = _rango_mes(anio, mes)
    comisiones_map = _totales_comisiones_vendedor(sucursal, fecha_desde, fecha_hasta)

    vendedores = list(
        Vendedor.objects.filter(sucursal=sucursal, is_active=True)
        .only(
            'id',
            'nombre',
            'apellido',
            'sueldo_basico',
            'basico_no_suma_si_comisiones_superan',
        )
        .order_by('apellido', 'nombre', 'id')
    )

    filas = []
    total_comisiones = Decimal('0')
    total_basicos_aplicados = Decimal('0')
    total_pagar = Decimal('0')

    for v in vendedores:
        comis = Decimal(str(comisiones_map.get(v.id, 0) or 0)).quantize(Decimal('0.01'))
        basico = Decimal(str(getattr(v, 'sueldo_basico', None) or 0)).quantize(Decimal('0.01'))
        flag = bool(getattr(v, 'basico_no_suma_si_comisiones_superan', False))
        total, basico_aplicado = total_a_pagar_productor(basico, comis, flag)
        basico_en_total = basico if basico_aplicado else Decimal('0')

        if comis == 0 and basico == 0:
            continue

        nombre = f'{(v.apellido or "").strip()}, {(v.nombre or "").strip()}'.strip(', ') or str(v)
        filas.append({
            'vendedor': v,
            'nombre': nombre,
            'comisiones': comis,
            'sueldo_basico': basico,
            'flag_no_suma_si_superan': flag,
            'basico_aplicado': basico_aplicado,
            'basico_en_total': basico_en_total,
            'total': total,
            'nota': (
                'Solo comisiones (superó el básico)'
                if flag and not basico_aplicado
                else ('Básico + comisiones' if basico > 0 else 'Solo comisiones')
            ),
        })
        total_comisiones += comis
        total_basicos_aplicados += basico_en_total
        total_pagar += total

    return {
        'anio': anio,
        'mes': mes,
        'mes_nombre': MESES_ES[mes] if 1 <= mes <= 12 else '',
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'filas': filas,
        'total_comisiones': total_comisiones,
        'total_basicos_aplicados': total_basicos_aplicados,
        'total_pagar': total_pagar,
    }
