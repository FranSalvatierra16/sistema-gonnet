"""Armado del resumen mensual de entradas y salidas (modelo cierre oficina)."""
import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from inmobiliaria.models import CategoriaGastoOficina, ComisionVendedor, GastoOficina, Vendedor
from inmobiliaria.models import LiquidacionPropietario
from inmobiliaria.oficina_gastos import RAICES_SUBCATEGORIAS_VENDEDOR, asegurar_estructura_cierre_oficina
from inmobiliaria.views_honorarios import _filas_honorarios_desde_liquidaciones, _filtrar_filas_por_fecha

MESES_ES = (
    '', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
)

MAPEO_HONORARIOS_INGRESOS = {
    'comision': 'Comisión por ventas',
    'cochera': 'Gastos bancarios',
    'fondo': 'Honorarios gestión cob.',
}


def _rango_mes(anio, mes):
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, 1), date(anio, mes, ultimo)


def _totales_gastos_por_categoria_ids(gastos_qs):
    ag = (
        gastos_qs.values('categoria_id')
        .annotate(total=Sum('monto'))
        .order_by()
    )
    return {row['categoria_id']: row['total'] or Decimal('0') for row in ag}


def _totales_comisiones_vendedor(sucursal, fecha_desde, fecha_hasta):
    """Comisiones pagadas en el mes (egreso al vendedor)."""
    qs = (
        ComisionVendedor.objects.filter(
            vendedor__sucursal=sucursal,
            estado='pagada',
            fecha_operacion__date__gte=fecha_desde,
            fecha_operacion__date__lte=fecha_hasta,
        )
        .values('vendedor_id')
        .annotate(total=Sum('monto_comision'))
    )
    return {row['vendedor_id']: row['total'] or Decimal('0') for row in qs}


def _honorarios_por_etiqueta(sucursal, fecha_desde, fecha_hasta):
    qs = (
        LiquidacionPropietario.objects.filter(sucursal=sucursal)
        .exclude(estado='cancelada')
        .select_related('propietario', 'propiedad', 'reserva', 'contrato')
    )
    qs = qs.filter(
        Q(fecha_creacion__date__gte=fecha_desde, fecha_creacion__date__lte=fecha_hasta)
        | Q(fecha_desde__gte=fecha_desde, fecha_desde__lte=fecha_hasta)
        | Q(reserva__fecha_inicio__gte=fecha_desde, reserva__fecha_inicio__lte=fecha_hasta)
        | Q(contrato__fecha_inicio__gte=fecha_desde, contrato__fecha_inicio__lte=fecha_hasta)
    ).distinct()
    filas = _filtrar_filas_por_fecha(
        _filas_honorarios_desde_liquidaciones(qs),
        fecha_desde,
        fecha_hasta,
    )
    totales = defaultdict(lambda: Decimal('0'))
    for f in filas:
        etiqueta = MAPEO_HONORARIOS_INGRESOS.get(f.get('tipo'), 'Comisión por ventas')
        totales[etiqueta] += f.get('monto') or Decimal('0')
    return dict(totales)


def construir_resumen_cierre(sucursal, anio, mes):
    asegurar_estructura_cierre_oficina(sucursal)
    fecha_desde, fecha_hasta = _rango_mes(anio, mes)

    gastos_qs = GastoOficina.objects.filter(
        sucursal=sucursal,
        fecha__gte=fecha_desde,
        fecha__lte=fecha_hasta,
    )
    totales_por_cat = _totales_gastos_por_categoria_ids(gastos_qs)
    comisiones_pagadas = _totales_comisiones_vendedor(sucursal, fecha_desde, fecha_hasta)
    honorarios_map = _honorarios_por_etiqueta(sucursal, fecha_desde, fecha_hasta)

    vendedores_map = {
        v.id: v
        for v in Vendedor.objects.filter(sucursal=sucursal).only('id', 'nombre', 'apellido')
    }

    bloques_egresos = []
    bloque_ingresos = None
    total_egresos = Decimal('0')
    total_ingresos = Decimal('0')

    raices = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent__isnull=True,
        activa=True,
    ).prefetch_related('subcategorias').order_by('orden', 'nombre')

    for raiz in raices:
        nombre_raiz = (raiz.nombre or '').strip()
        if nombre_raiz.lower() == 'ingresos':
            filas = []
            hijos = [h for h in raiz.subcategorias.all() if h.activa]
            hijos.sort(key=lambda x: (x.orden, x.nombre))
            for hijo in hijos:
                monto_gasto = totales_por_cat.get(hijo.id, Decimal('0'))
                monto_hon = honorarios_map.get(hijo.nombre, Decimal('0'))
                monto = monto_hon
                if monto_gasto < 0:
                    monto += abs(monto_gasto)
                elif monto_gasto > 0:
                    monto += monto_gasto
                filas.append({'nombre': hijo.nombre, 'monto': monto})
            total_bloque = sum((f['monto'] for f in filas), Decimal('0'))
            total_ingresos += total_bloque
            bloque_ingresos = {
                'titulo': 'INGRESOS',
                'filas': filas,
                'total': total_bloque,
            }
            continue

        filas = []
        hijos = [h for h in raiz.subcategorias.all() if h.activa]
        hijos.sort(key=lambda x: (x.orden, x.nombre))
        for hijo in hijos:
            monto = totales_por_cat.get(hijo.id, Decimal('0'))
            if nombre_raiz == 'Comisiones vendedores' and hijo.vendedor_id:
                monto += comisiones_pagadas.get(hijo.vendedor_id, Decimal('0'))
            if monto > 0:
                filas.append({'nombre': hijo.nombre, 'monto': monto})

        if nombre_raiz == 'Comisiones vendedores':
            usados = {h.vendedor_id for h in hijos if h.vendedor_id}
            for vid, monto in comisiones_pagadas.items():
                if vid in usados or monto <= 0:
                    continue
                v = vendedores_map.get(vid)
                nombre = str(v) if v else f'Vendedor #{vid}'
                filas.append({'nombre': nombre, 'monto': monto})

        total_bloque = sum((f['monto'] for f in filas), Decimal('0'))
        if filas or nombre_raiz in RAICES_SUBCATEGORIAS_VENDEDOR:
            bloques_egresos.append({
                'titulo': nombre_raiz.upper(),
                'filas': filas,
                'total': total_bloque,
            })
            total_egresos += total_bloque

    saldo = total_ingresos - total_egresos

    return {
        'anio': anio,
        'mes': mes,
        'mes_label': f'{MESES_ES[mes]} {anio}',
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'bloques_egresos': bloques_egresos,
        'bloque_ingresos': bloque_ingresos,
        'total_egresos': total_egresos,
        'total_ingresos': total_ingresos,
        'saldo': saldo,
        'sucursal': sucursal,
    }
