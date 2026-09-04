"""Armado del resumen mensual de entradas y salidas (modelo cierre oficina)."""
import calendar
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum

from inmobiliaria.models import (
    CategoriaGastoOficina,
    ComisionVendedor,
    Disponibilidad,
    GastoOficina,
    LiquidacionPropietario,
    OperacionVenta,
    Vendedor,
)
from inmobiliaria.oficina_gastos import (
    RAICES_SUBCATEGORIAS_VENDEDOR,
    _norm_nombre_cat,
    nombre_raiz_es_extension_cierre,
    signo_fondo_oscar,
)
from inmobiliaria.views_honorarios import (
    _filas_honorarios_desde_caratulas_confirmadas,
    _filas_honorarios_desde_liquidaciones,
    _filas_honorarios_oficina_desde_caratulas_contrato,
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
    """
    Totales del mes por vendedor, misma base que el resumen mensual del productor:
    comisiones visibles en historial (confirmadas/pagadas/pendientes de carátula, + ventas).
    """
    from inmobiliaria.models.comision import q_comision_operacion_de_sucursal

    qs = (
        ComisionVendedor.objects.filter(
            fecha_operacion__date__gte=fecha_desde,
            fecha_operacion__date__lte=fecha_hasta,
        )
        .filter(q_comision_operacion_de_sucursal(sucursal))
        .visibles_en_historial()
        .values('vendedor_id')
        .annotate(total=Sum('monto_comision'))
    )
    return {row['vendedor_id']: row['total'] or Decimal('0') for row in qs}


def _etiqueta_ingreso_desde_fila_honorario(fila):
    """
    Asigna una fila de honorarios a la subcategoría de Ingresos del cierre.
    Fondo y cochera no van acá: el fondo va a «Recaudación fondos».
    Tasación / Gastos bancarios / Honorarios Marbella quedan para carga manual.
    """
    tipo = (fila.get('tipo') or '').strip()
    cat = (fila.get('categoria_operacion') or '').strip().lower()

    # Fondo → Recaudación fondos; cochera no es ingreso de comisión de oficina.
    if tipo in ('fondo', 'cochera'):
        return None

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
    filas_oficina_cto = _filas_honorarios_oficina_desde_caratulas_contrato(
        sucursal, fecha_desde, fecha_hasta
    )
    return _filtrar_filas_por_fecha(
        list(filas_liq) + list(filas_car) + list(filas_oficina_res) + list(filas_oficina_cto),
        fecha_desde,
        fecha_hasta,
    )


def _honorarios_ventas_cerradas(sucursal, fecha_desde, fecha_hasta):
    """Honorarios ARS de ventas cerradas confirmadas en el mes (fecha de venta)."""
    if not sucursal or not fecha_desde or not fecha_hasta:
        return Decimal('0')
    total = (
        OperacionVenta.objects.filter(
            sucursal=sucursal,
            estado='confirmada',
            fecha_venta__gte=fecha_desde,
            fecha_venta__lte=fecha_hasta,
        ).aggregate(t=Sum('honorarios_ars'))['t']
        or Decimal('0')
    )
    return Decimal(str(total))


def _honorarios_por_etiqueta(sucursal, fecha_desde, fecha_hasta):
    """
    Totales de comisiones de oficina por etiqueta de Ingresos, más fondo/cochera
    (para Recaudación fondos y usos auxiliares).
    Retorna ``(mapa_ingresos, total_fondo, total_cochera)``.
    """
    try:
        filas = _filas_honorarios_para_cierre(sucursal, fecha_desde, fecha_hasta)
        totales = defaultdict(lambda: Decimal('0'))
        total_fondo = Decimal('0')
        total_cochera = Decimal('0')
        ops_comision_contrato = {
            (f.get('operacion_kind'), f.get('operacion_pk'))
            for f in filas
            if f.get('tipo') == 'comision'
            and f.get('operacion_kind') == 'contrato'
            and f.get('operacion_pk')
        }
        for f in filas:
            try:
                monto = Decimal(str(f.get('monto') or 0))
            except Exception:
                continue
            if monto == 0:
                continue
            tipo = (f.get('tipo') or '').strip()
            if tipo == 'fondo':
                total_fondo += monto
                continue
            if tipo == 'cochera':
                total_cochera += monto
                continue
            etiqueta = _etiqueta_ingreso_desde_fila_honorario(f)
            if not etiqueta:
                continue
            # Contratos: inmobiliaria ya es locador+locatario; no contar las dos.
            if (
                tipo == 'comisiones_locador_locatario'
                and f.get('operacion_kind') == 'contrato'
                and (f.get('operacion_kind'), f.get('operacion_pk')) in ops_comision_contrato
            ):
                continue
            totales[etiqueta] += monto

        # Ventas cerradas (OperacionVenta): honorarios en pesos → Comisión por ventas
        ventas_ars = _honorarios_ventas_cerradas(sucursal, fecha_desde, fecha_hasta)
        if ventas_ars:
            totales[ETIQUETA_COMISION_VENTAS] += ventas_ars

        return dict(totales), total_fondo.quantize(Decimal('0.01')), total_cochera.quantize(
            Decimal('0.01')
        )
    except Exception:
        logger.exception(
            'resumen_cierre: falló honorarios (sucursal_id=%s, %s-%02d)',
            getattr(sucursal, 'pk', None),
            fecha_desde.year if fecha_desde else '?',
            fecha_desde.month if fecha_desde else 0,
        )
        return {}, Decimal('0'), Decimal('0')


def _monto_honorarios_etiqueta(honorarios_map, nombre_categoria):
    """Busca monto por nombre exacto o normalizado (ej. Comisión por ventas)."""
    if not honorarios_map:
        return Decimal('0')
    if nombre_categoria in honorarios_map:
        return honorarios_map.get(nombre_categoria) or Decimal('0')
    clave = _norm_nombre_cat(nombre_categoria)
    for k, v in honorarios_map.items():
        if _norm_nombre_cat(k) == clave:
            return v or Decimal('0')
    return Decimal('0')


def _monto_absoluto_cat(totales_por_cat, cat_id):
    return abs(totales_por_cat.get(cat_id, Decimal('0')) or Decimal('0'))


def _hijos_activos(raiz):
    hijos = [h for h in raiz.subcategorias.all() if h.activa]
    hijos.sort(key=lambda x: (x.orden, x.nombre))
    return hijos


def _liquidacion_solapa_rango(liq, d1, d2):
    """True si el período de la liquidación intersecta [d1, d2]."""
    from django.utils import timezone as dj_tz

    fc = None
    if getattr(liq, 'fecha_creacion', None):
        try:
            fc = dj_tz.localdate(liq.fecha_creacion)
        except (ValueError, TypeError, OverflowError):
            fc = liq.fecha_creacion.date() if hasattr(liq.fecha_creacion, 'date') else None
    start = liq.fecha_desde
    end = liq.fecha_hasta
    if start is None and end is None:
        if fc is None:
            return False
        start = end = fc
    elif start is None:
        start = end if end is not None else fc
        if start is None:
            return False
        if end is None:
            end = start
    elif end is None:
        end = start
    return start <= d2 and end >= d1


def _saldo_cierre_dptos_tomados(sucursal, fecha_desde, fecha_hasta):
    """
    Saldo del reporte de departamentos tomados (asegurados) en el mes:
    suma (liquidado al propietario − monto asegurado) en ARS.
    """
    try:
        disps = list(
            Disponibilidad.objects.filter(
                asegurado=True,
                propiedad__sucursal=sucursal,
                fecha_inicio__lte=fecha_hasta,
                fecha_fin__gte=fecha_desde,
            ).select_related('propiedad')
        )
    except Exception:
        logger.exception(
            'resumen_cierre: falló listado dptos. tomados (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )
        return Decimal('0')

    tot_saldo = Decimal('0')
    for disp in disps:
        if (disp.moneda_asegurado or 'ARS').upper() != 'ARS':
            continue
        pagado = Decimal(str(disp.monto_asegurado or 0))
        cobrado = Decimal('0')
        liqs = (
            LiquidacionPropietario.objects.filter(
                propiedad=disp.propiedad,
                sucursal=sucursal,
            )
            .exclude(estado='cancelada')
            .only('monto_propietario', 'fecha_desde', 'fecha_hasta', 'fecha_creacion', 'estado')
        )
        d1, d2 = disp.fecha_inicio, disp.fecha_fin
        for liq in liqs:
            if not _liquidacion_solapa_rango(liq, d1, d2):
                continue
            cobrado += liq.monto_propietario or Decimal('0')
        tot_saldo += (cobrado - pagado).quantize(Decimal('0.01'))
    return tot_saldo.quantize(Decimal('0.01'))


def _bloque_extension_suma(raiz, totales_por_cat, titulo=None, extras_por_nombre=None):
    """Filas con monto absoluto (ingresos/egresos de extensión)."""
    extras_por_nombre = extras_por_nombre or {}
    filas = []
    for hijo in _hijos_activos(raiz):
        monto = _monto_absoluto_cat(totales_por_cat, hijo.id)
        extra = Decimal('0')
        clave = _norm_nombre_cat(hijo.nombre)
        for nombre_extra, monto_extra in extras_por_nombre.items():
            if _norm_nombre_cat(nombre_extra) == clave:
                extra = Decimal(str(monto_extra or 0))
                break
        monto = (monto + extra).quantize(Decimal('0.01'))
        filas.append({'nombre': hijo.nombre, 'monto': monto, 'signo': 1})
    if not filas and not raiz.subcategorias.exists():
        monto = _monto_absoluto_cat(totales_por_cat, raiz.id)
        filas.append({'nombre': raiz.nombre, 'monto': monto, 'signo': 1})
    # Si no hay subcategoría «Fondo mantenimiento» pero sí hay total de honorarios, forzar fila.
    usados = {_norm_nombre_cat(f['nombre']) for f in filas}
    for nombre_extra, monto_extra in extras_por_nombre.items():
        monto_e = Decimal(str(monto_extra or 0))
        if monto_e == 0:
            continue
        if _norm_nombre_cat(nombre_extra) in usados:
            continue
        filas.append({'nombre': nombre_extra, 'monto': monto_e, 'signo': 1})
    total = sum((f['monto'] for f in filas), Decimal('0'))
    return {
        'titulo': (titulo or raiz.nombre or '').upper(),
        'filas': filas,
        'total': total,
    }


def _bloque_fondo_oscar(raiz, totales_por_cat):
    filas = []
    total = Decimal('0')
    for hijo in _hijos_activos(raiz):
        signo = signo_fondo_oscar(hijo.nombre)
        monto = _monto_absoluto_cat(totales_por_cat, hijo.id)
        firmado = (monto * Decimal(signo)).quantize(Decimal('0.01'))
        filas.append({
            'nombre': hijo.nombre,
            'monto': monto,
            'monto_firmado': firmado,
            'signo': signo,
        })
        total += firmado
    return {
        'titulo': 'FONDO OSCAR',
        'filas': filas,
        'total': total.quantize(Decimal('0.01')),
    }


def construir_resumen_cierre(sucursal, anio, mes):
    # El sync de categorías lo hace la vista con try/except; no repetirlo acá
    # (IntegrityError / unique en sync tumba la pantalla con 500).
    fecha_desde, fecha_hasta = _rango_mes(anio, mes)

    gastos_qs = GastoOficina.objects.filter(
        sucursal=sucursal,
        fecha__gte=fecha_desde,
        fecha__lte=fecha_hasta,
    )
    try:
        from inmobiliaria.oficina_gastos import sincronizar_gastos_oficina_desde_conceptos_caja

        sincronizar_gastos_oficina_desde_conceptos_caja(sucursal, fecha_desde, fecha_hasta)
        gastos_qs = GastoOficina.objects.filter(
            sucursal=sucursal,
            fecha__gte=fecha_desde,
            fecha__lte=fecha_hasta,
        )
    except Exception:
        logger.exception(
            'resumen_cierre: falló sync conceptos→oficina (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )
    totales_por_cat = _totales_gastos_por_categoria_ids(gastos_qs)
    # Veraz / Bancos (concepto 22): neto desde caja + cargas manuales.
    # Ingresos › Gastos bancarios queda para carga manual de oficina (no se pisa).
    try:
        from inmobiliaria.oficina_gastos import (
            MAPA_CONCEPTOS_CAJA_A_OFICINA,
            MAPA_NOMBRE_CONCEPTO_A_OFICINA,
            _neto_gastos_oficina_desde_caja_mapeada,
            _norm_nombre_cat as _norm_of,
            _reubicar_gastos_bancarios_mal_categorizados,
        )

        try:
            _reubicar_gastos_bancarios_mal_categorizados(
                sucursal, fecha_desde, fecha_hasta
            )
            # Releer totales tras reubicar.
            gastos_qs = GastoOficina.objects.filter(
                sucursal=sucursal,
                fecha__gte=fecha_desde,
                fecha__lte=fecha_hasta,
            )
            totales_por_cat = _totales_gastos_por_categoria_ids(gastos_qs)
        except Exception:
            logger.exception(
                'resumen_cierre: falló reubicar gastos bancarios (sucursal_id=%s)',
                getattr(sucursal, 'pk', None),
            )

        netos_mapa = _neto_gastos_oficina_desde_caja_mapeada(
            sucursal, fecha_desde, fecha_hasta
        )
        nombres_mapeados = {
            _norm_of(sub)
            for _r, sub in (
                set(MAPA_CONCEPTOS_CAJA_A_OFICINA.values())
                | set(MAPA_NOMBRE_CONCEPTO_A_OFICINA.values())
            )
        }
        cats_mapeadas_ids = set()
        for cat in CategoriaGastoOficina.objects.filter(
            sucursal=sucursal, activa=True, parent__isnull=False
        ).only('id', 'nombre'):
            if _norm_of(cat.nombre) in nombres_mapeados:
                cats_mapeadas_ids.add(cat.id)
                totales_por_cat[cat.id] = Decimal('0')
        for cat_id, neto in netos_mapa.items():
            totales_por_cat[cat_id] = neto
        if cats_mapeadas_ids:
            for row in (
                GastoOficina.objects.filter(
                    sucursal=sucursal,
                    categoria_id__in=cats_mapeadas_ids,
                    fecha__gte=fecha_desde,
                    fecha__lte=fecha_hasta,
                    movimiento_caja__isnull=True,
                )
                .values('categoria_id')
                .annotate(total=Sum('monto'))
            ):
                cid = row['categoria_id']
                extras = Decimal(str(row['total'] or 0))
                totales_por_cat[cid] = (
                    Decimal(str(totales_por_cat.get(cid, 0) or 0)) + extras
                ).quantize(Decimal('0.01'))
    except Exception:
        logger.exception(
            'resumen_cierre: falló neto caja mapeada (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )

    try:
        comisiones_pagadas = _totales_comisiones_vendedor(sucursal, fecha_desde, fecha_hasta)
    except Exception:
        logger.exception(
            'resumen_cierre: falló comisiones (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )
        comisiones_pagadas = {}
    honorarios_map, total_fondo_mant, _total_cochera = _honorarios_por_etiqueta(
        sucursal, fecha_desde, fecha_hasta
    )

    vendedores_map = {
        v.id: v
        for v in Vendedor.objects.filter(sucursal=sucursal).only('id', 'nombre', 'apellido')
    }

    bloques_egresos = []
    bloque_ingresos = None
    total_egresos = Decimal('0')
    total_ingresos = Decimal('0')

    bloque_recaudacion = None
    bloque_cierre_tomados = None
    bloque_fondo_oscar = None
    bloque_gastos_oscar = None

    raices = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent__isnull=True,
        activa=True,
    ).prefetch_related('subcategorias').order_by('orden', 'nombre')

    for raiz in raices:
        nombre_raiz = (raiz.nombre or '').strip()
        nombre_norm = _norm_nombre_cat(nombre_raiz)

        if nombre_raiz_es_extension_cierre(nombre_raiz):
            if nombre_norm == 'recaudacion fondos':
                bloque_recaudacion = _bloque_extension_suma(
                    raiz,
                    totales_por_cat,
                    titulo='RECAUDACIÓN FONDOS',
                    extras_por_nombre={
                        'Fondo mantenimiento': total_fondo_mant,
                    },
                )
            elif nombre_norm in ('cierre dptos. tomados', 'cierre dptos tomados'):
                bloque = _bloque_extension_suma(
                    raiz, totales_por_cat, titulo='CIERRE DPTOS. TOMADOS'
                )
                if bloque['total'] == 0:
                    auto = _saldo_cierre_dptos_tomados(sucursal, fecha_desde, fecha_hasta)
                    bloque['filas'] = [{
                        'nombre': 'Cierre dptos. tomados',
                        'monto': auto,
                        'signo': 1,
                    }]
                    bloque['total'] = auto
                    bloque['origen'] = 'reporte_asegurados'
                else:
                    bloque['origen'] = 'caja'
                bloque_cierre_tomados = bloque
            elif nombre_norm == 'fondo oscar':
                bloque_fondo_oscar = _bloque_fondo_oscar(raiz, totales_por_cat)
            elif nombre_norm == 'gastos oscar':
                bloque_gastos_oscar = _bloque_extension_suma(
                    raiz, totales_por_cat, titulo='GASTOS OSCAR'
                )
            continue

        if nombre_raiz.lower() == 'ingresos':
            filas = []
            hijos = _hijos_activos(raiz)
            for hijo in hijos:
                monto_gasto = totales_por_cat.get(hijo.id, Decimal('0'))
                monto_hon = _monto_honorarios_etiqueta(honorarios_map, hijo.nombre)
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
        hijos = _hijos_activos(raiz)
        for hijo in hijos:
            if nombre_raiz == 'Comisiones vendedores' and hijo.vendedor_id:
                # Solo ComisionVendedor (igual que el historial del productor).
                # No sumar GastoOficina de esa categoría: suele ser el mismo egreso duplicado.
                monto = comisiones_pagadas.get(hijo.vendedor_id, Decimal('0'))
            else:
                monto = totales_por_cat.get(hijo.id, Decimal('0'))
            # Incluir netos ≠ 0 (ej. Veraz con egresos e ingresos de caja).
            if monto != 0:
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

    # Fallbacks si aún no se sincronizó el árbol de extensión.
    if bloque_recaudacion is None:
        filas_fondo = []
        if total_fondo_mant:
            filas_fondo.append({
                'nombre': 'Fondo mantenimiento',
                'monto': total_fondo_mant,
                'signo': 1,
            })
        bloque_recaudacion = {
            'titulo': 'RECAUDACIÓN FONDOS',
            'filas': filas_fondo,
            'total': total_fondo_mant,
        }
    if bloque_cierre_tomados is None:
        auto = _saldo_cierre_dptos_tomados(sucursal, fecha_desde, fecha_hasta)
        bloque_cierre_tomados = {
            'titulo': 'CIERRE DPTOS. TOMADOS',
            'filas': [{'nombre': 'Cierre dptos. tomados', 'monto': auto, 'signo': 1}],
            'total': auto,
            'origen': 'reporte_asegurados',
        }
    if bloque_fondo_oscar is None:
        bloque_fondo_oscar = {'titulo': 'FONDO OSCAR', 'filas': [], 'total': Decimal('0')}
    if bloque_gastos_oscar is None:
        bloque_gastos_oscar = {'titulo': 'GASTOS OSCAR', 'filas': [], 'total': Decimal('0')}

    saldo = total_ingresos - total_egresos
    total_gral_ofic_fondo_tomados = (
        saldo + bloque_recaudacion['total'] + bloque_cierre_tomados['total']
    ).quantize(Decimal('0.01'))
    resultado_financiero_oscar = (
        total_gral_ofic_fondo_tomados
        + bloque_fondo_oscar['total']
        - bloque_gastos_oscar['total']
    ).quantize(Decimal('0.01'))

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
        'bloque_recaudacion': bloque_recaudacion,
        'bloque_cierre_tomados': bloque_cierre_tomados,
        'total_gral_ofic_fondo_tomados': total_gral_ofic_fondo_tomados,
        'bloque_fondo_oscar': bloque_fondo_oscar,
        'bloque_gastos_oscar': bloque_gastos_oscar,
        'resultado_financiero_oscar': resultado_financiero_oscar,
        'sucursal': sucursal,
    }
