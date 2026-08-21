"""Armado del resumen mensual de entradas y salidas (modelo cierre oficina)."""
import calendar
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from inmobiliaria.models import CategoriaGastoOficina, ComisionVendedor, GastoOficina, Vendedor
from inmobiliaria.models import LiquidacionPropietario
from inmobiliaria.oficina_gastos import RAICES_SUBCATEGORIAS_VENDEDOR
from inmobiliaria.views_honorarios import (
    _filas_honorarios_desde_caratulas_confirmadas,
    _filas_honorarios_desde_liquidaciones,
    _filas_honorarios_oficina_desde_caratulas_reserva,
    _filtrar_filas_por_fecha,
    _keys_comisiones_contrato_cubiertas,
)

logger = logging.getLogger(__name__)

MESES_ES = (
    '', 'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
)

# Subcategorías de Ingresos (seed PDF) alimentadas desde honorarios/liquidaciones.
ETIQUETA_COMISION_VENTAS = 'Comisión por ventas'
ETIQUETA_24 = '24 meses'
ETIQUETA_TEMPORARIOS = 'Com. alq. temporarios'
ETIQUETA_ANIO_INVIERNO = 'Com. alq. año e invierno'
ETIQUETA_GESTION_COB = 'Honorarios gestión cob.'


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


def _etiqueta_ingreso_desde_fila_honorario(fila):
    """
    Asigna una fila de honorarios a la subcategoría de Ingresos del cierre.
    Tasación / Gastos bancarios / Honorarios Marbella quedan para carga manual.
    """
    tipo = (fila.get('tipo') or '').strip()
    cat = (fila.get('categoria_operacion') or '').strip().lower()

    if tipo in ('fondo', 'cochera'):
        return ETIQUETA_GESTION_COB

    if tipo not in ('comision', 'comisiones_locador_locatario'):
        return None

    if cat in ('dia', 'estudiante'):
        return ETIQUETA_TEMPORARIOS
    if cat in ('invierno', '6'):
        return ETIQUETA_ANIO_INVIERNO
    if cat == '24':
        return ETIQUETA_24
    if cat in ('venta', 'ventas'):
        return ETIQUETA_COMISION_VENTAS
    # Sin tipo claro: ventas / genérico.
    return ETIQUETA_COMISION_VENTAS


def _filas_honorarios_para_cierre(sucursal, fecha_desde, fecha_hasta):
    """Mismas fuentes que el listado de honorarios de oficina (liq + carátulas)."""
    qs = (
        LiquidacionPropietario.objects.filter(sucursal=sucursal)
        .select_related('propietario', 'propiedad', 'reserva', 'contrato')
    )
    qs = qs.filter(
        Q(fecha_creacion__date__gte=fecha_desde, fecha_creacion__date__lte=fecha_hasta)
        | Q(fecha_desde__gte=fecha_desde, fecha_desde__lte=fecha_hasta)
        | Q(reserva__fecha_inicio__gte=fecha_desde, reserva__fecha_inicio__lte=fecha_hasta)
        | Q(reserva__fecha_creacion__date__gte=fecha_desde, reserva__fecha_creacion__date__lte=fecha_hasta)
        | Q(contrato__fecha_inicio__gte=fecha_desde, contrato__fecha_inicio__lte=fecha_hasta)
        | Q(
            fecha_procesamiento__date__gte=fecha_desde,
            fecha_procesamiento__date__lte=fecha_hasta,
            estado='cancelada',
        )
    ).distinct()

    filas_liq = _filtrar_filas_por_fecha(
        _filas_honorarios_desde_liquidaciones(qs),
        fecha_desde,
        fecha_hasta,
    )
    cubiertos = _keys_comisiones_contrato_cubiertas(filas_liq)
    filas_car = _filas_honorarios_desde_caratulas_confirmadas(
        sucursal, fecha_desde, fecha_hasta, cubiertos
    )
    filas_oficina_res = _filas_honorarios_oficina_desde_caratulas_reserva(
        sucursal, fecha_desde, fecha_hasta
    )
    return _filtrar_filas_por_fecha(
        list(filas_liq) + list(filas_car) + list(filas_oficina_res),
        fecha_desde,
        fecha_hasta,
    )


def _honorarios_por_etiqueta(sucursal, fecha_desde, fecha_hasta):
    try:
        filas = _filas_honorarios_para_cierre(sucursal, fecha_desde, fecha_hasta)
        totales = defaultdict(lambda: Decimal('0'))
        for f in filas:
            etiqueta = _etiqueta_ingreso_desde_fila_honorario(f)
            if not etiqueta:
                continue
            try:
                monto = Decimal(str(f.get('monto') or 0))
            except Exception:
                continue
            if monto == 0:
                continue
            totales[etiqueta] += monto
        return dict(totales)
    except Exception:
        logger.exception(
            'resumen_cierre: falló honorarios (sucursal_id=%s, %s-%02d)',
            getattr(sucursal, 'pk', None),
            fecha_desde.year if fecha_desde else '?',
            fecha_desde.month if fecha_desde else 0,
        )
        return {}


def construir_resumen_cierre(sucursal, anio, mes):
    # El sync de categorías lo hace la vista con try/except; no repetirlo acá
    # (IntegrityError / unique en sync tumba la pantalla con 500).
    fecha_desde, fecha_hasta = _rango_mes(anio, mes)

    gastos_qs = GastoOficina.objects.filter(
        sucursal=sucursal,
        fecha__gte=fecha_desde,
        fecha__lte=fecha_hasta,
    )
    totales_por_cat = _totales_gastos_por_categoria_ids(gastos_qs)
    try:
        comisiones_pagadas = _totales_comisiones_vendedor(sucursal, fecha_desde, fecha_hasta)
    except Exception:
        logger.exception(
            'resumen_cierre: falló comisiones (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )
        comisiones_pagadas = {}
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
