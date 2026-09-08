"""Liquidación mensual de productores: sueldo básico + comisiones."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models import (
    ComisionVendedor,
    CuadroHonorariosColumna,
    SueldoBasicoVigencia,
    Vendedor,
)
from inmobiliaria.oficina_resumen import MESES_ES, _rango_mes

CLAVES_COMISION = (
    'honorarios',
    'por_dia',
    'por_invierno',
    'por_24_meses',
    'por_venta',
    'otros',
)


def _desglose_vacio():
    d = {k: Decimal('0.00') for k in CLAVES_COMISION}
    d['total'] = Decimal('0.00')
    return d


def _clave_desglose_comision(comision):
    """Misma clasificación que el historial / carátula."""
    cat, sub = comision.clasificacion_listado()
    if sub in ('primer', 'segundo', 'fichaje_venta'):
        return 'honorarios'
    if cat == 'por_dia':
        return 'por_dia'
    if cat == 'por_invierno':
        return 'por_invierno'
    if cat == 'por_24_meses':
        return 'por_24_meses'
    if cat == 'por_venta':
        return 'por_venta'
    return 'otros'


def comisiones_desglose_vendedores(sucursal, fecha_desde, fecha_hasta):
    """Totales del mes por vendedor y tipo (honorarios/fichaje, día, invierno, 24, venta)."""
    from inmobiliaria.models.comision import q_comision_operacion_de_sucursal

    qs = (
        ComisionVendedor.objects.filter(
            fecha_operacion__date__gte=fecha_desde,
            fecha_operacion__date__lte=fecha_hasta,
        )
        .filter(q_comision_operacion_de_sucursal(sucursal))
        .visibles_en_historial()
        .select_related(
            'vendedor',
            'reserva',
            'reserva__propiedad',
            'contrato',
        )
    )
    out = defaultdict(_desglose_vacio)
    for c in qs:
        monto = Decimal(str(c.monto_comision or 0)).quantize(Decimal('0.01'))
        row = out[c.vendedor_id]
        clave = _clave_desglose_comision(c)
        row[clave] += monto
        row['total'] += monto
    return out

# Vigencia “desde siempre” para no pisar meses anteriores al primer aumento.
FECHA_VIGENCIA_INICIAL = date(2000, 1, 1)


def primer_dia_mes(anio, mes):
    return date(int(anio), int(mes), 1)


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


def sueldos_basicos_vigentes(vendedor_ids, anio, mes, fallbacks):
    """
    Básico de cada vendedor para el mes: última vigencia con
    vigente_desde <= 1° de ese mes. Si no hay, usa el fallback (ficha).
    """
    ids = list(vendedor_ids)
    result = {}
    if not ids:
        return result

    corte = primer_dia_mes(anio, mes)
    filas = (
        SueldoBasicoVigencia.objects
        .filter(vendedor_id__in=ids, vigente_desde__lte=corte)
        .order_by('vendedor_id', '-vigente_desde')
        .values_list('vendedor_id', 'monto')
    )
    vistos = set()
    for vid, monto in filas:
        if vid in vistos:
            continue
        vistos.add(vid)
        result[vid] = Decimal(str(monto or 0)).quantize(Decimal('0.01'))

    for vid in ids:
        if vid not in result:
            result[vid] = Decimal(str(fallbacks.get(vid) or 0)).quantize(Decimal('0.01'))
    return result


def guardar_sueldo_basico_desde_mes(vendedor, anio, mes, monto_nuevo):
    """
    Fija el básico desde el mes indicado en adelante.
    Los meses anteriores no cambian (si no había historial, se siembra el valor viejo).
    """
    monto_nuevo = Decimal(str(monto_nuevo or 0)).quantize(Decimal('0.01'))
    desde = primer_dia_mes(anio, mes)
    fallback = {vendedor.id: getattr(vendedor, 'sueldo_basico', None)}
    monto_actual = sueldos_basicos_vigentes([vendedor.id], anio, mes, fallback)[vendedor.id]
    if monto_actual == monto_nuevo:
        return False

    with transaction.atomic():
        hay_anterior = SueldoBasicoVigencia.objects.filter(
            vendedor=vendedor,
            vigente_desde__lt=desde,
        ).exists()
        if not hay_anterior and desde > FECHA_VIGENCIA_INICIAL:
            SueldoBasicoVigencia.objects.create(
                vendedor=vendedor,
                vigente_desde=FECHA_VIGENCIA_INICIAL,
                monto=monto_actual,
            )

        SueldoBasicoVigencia.objects.update_or_create(
            vendedor=vendedor,
            vigente_desde=desde,
            defaults={'monto': monto_nuevo},
        )
        SueldoBasicoVigencia.objects.filter(
            vendedor=vendedor,
            vigente_desde__gt=desde,
        ).delete()

        vendedor.sueldo_basico = monto_nuevo
        vendedor.save(update_fields=['sueldo_basico'])
    return True


def guardar_sueldos_basicos_mes(sucursal, anio, mes, post_data):
    """Lee basico_<id> del POST y guarda solo los que cambiaron. Devuelve cuántos se actualizaron."""
    montos = {}
    prefix = 'basico_'
    for key, raw in post_data.items():
        if not str(key).startswith(prefix):
            continue
        try:
            vid = int(str(key)[len(prefix):])
        except (TypeError, ValueError):
            continue
        montos[vid] = parse_decimal_monto(raw).quantize(Decimal('0.01'))

    if not montos:
        return 0

    vendedores = list(
        Vendedor.objects.filter(sucursal=sucursal, is_active=True, id__in=montos.keys())
    )
    cambiados = 0
    for v in vendedores:
        if guardar_sueldo_basico_desde_mes(v, anio, mes, montos[v.id]):
            cambiados += 1
    return cambiados


def construir_liquidacion_productores(sucursal, anio, mes):
    """
    Filas por vendedor activo de la sucursal para el mes:
    comisiones, básico vigente ese mes, si se sumó el básico, total a pagar.
    """
    fecha_desde, fecha_hasta = _rango_mes(anio, mes)
    desglose_map = comisiones_desglose_vendedores(sucursal, fecha_desde, fecha_hasta)

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

    fallbacks = {v.id: getattr(v, 'sueldo_basico', None) for v in vendedores}
    basicos = sueldos_basicos_vigentes([v.id for v in vendedores], anio, mes, fallbacks)

    filas = []
    tot_desglose = _desglose_vacio()
    total_basicos_aplicados = Decimal('0')
    total_pagar = Decimal('0')

    for v in vendedores:
        desg = desglose_map.get(v.id) or _desglose_vacio()
        comis = desg['total']
        basico = basicos.get(v.id, Decimal('0.00'))
        flag = bool(getattr(v, 'basico_no_suma_si_comisiones_superan', False))
        total, basico_aplicado = total_a_pagar_productor(basico, comis, flag)
        basico_en_total = basico if basico_aplicado else Decimal('0')

        if comis == 0 and basico == 0:
            continue

        nombre = f'{(v.apellido or "").strip()}, {(v.nombre or "").strip()}'.strip(', ') or str(v)
        filas.append({
            'vendedor': v,
            'nombre': nombre,
            'honorarios': desg['honorarios'],
            'por_dia': desg['por_dia'],
            'por_invierno': desg['por_invierno'],
            'por_24_meses': desg['por_24_meses'],
            'por_venta': desg['por_venta'],
            'otros': desg['otros'],
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
        for k in CLAVES_COMISION:
            tot_desglose[k] += desg[k]
        tot_desglose['total'] += comis
        total_basicos_aplicados += basico_en_total
        total_pagar += total

    return {
        'anio': anio,
        'mes': mes,
        'mes_nombre': MESES_ES[mes] if 1 <= mes <= 12 else '',
        'fecha_desde': fecha_desde,
        'fecha_hasta': fecha_hasta,
        'filas': filas,
        'total_honorarios': tot_desglose['honorarios'],
        'total_por_dia': tot_desglose['por_dia'],
        'total_por_invierno': tot_desglose['por_invierno'],
        'total_por_24_meses': tot_desglose['por_24_meses'],
        'total_por_venta': tot_desglose['por_venta'],
        'total_otros': tot_desglose['otros'],
        'total_comisiones': tot_desglose['total'],
        'total_basicos_aplicados': total_basicos_aplicados,
        'total_pagar': total_pagar,
    }


def _d(val):
    return Decimal(str(val or 0)).quantize(Decimal('0.01'))


def _col_label_vendedor(v):
    nom = (v.nombre or '').strip().upper()
    if nom:
        return nom
    return ((v.apellido or '').strip().upper() or f'#{v.id}')


def _label_venta(op):
    prop = getattr(op, 'propiedad', None)
    propietario = ''
    if prop is not None:
        dueño = getattr(prop, 'propietario', None)
        if dueño:
            propietario = (getattr(dueño, 'apellido', None) or getattr(dueño, 'nombre', None) or '').strip()
        if not propietario:
            propietario = (getattr(prop, 'direccion', None) or '').strip()
    comprador = (getattr(op, 'comprador_nombre', None) or '').strip()
    if propietario and comprador:
        return f'{propietario} - {comprador}'
    return comprador or propietario or f'Venta #{op.id}'


def _celdas(n, oficina=None, por_id=None, columnas=None):
    vals = [None] * n
    if oficina is not None and _d(oficina) != 0:
        vals[0] = _d(oficina)
    if por_id and columnas:
        for i, col in enumerate(columnas):
            vid = col.get('vid')
            if vid and vid in por_id:
                monto = _d(por_id[vid])
                vals[i] = monto if monto != 0 else None
    return vals


def _sumar_celdas(lista_celdas, n):
    tot = [_d(0) for _ in range(n)]
    for celdas in lista_celdas:
        if not celdas:
            continue
        for i, v in enumerate(celdas):
            if v is not None:
                tot[i] += _d(v)
    return tot


def _vendedores_activos_sucursal(sucursal):
    return list(
        Vendedor.objects.filter(sucursal=sucursal, is_active=True)
        .order_by('apellido', 'nombre', 'id')
    )


def ids_columnas_vendedores(sucursal):
    """IDs guardados para la planilla. Set vacío = todavía no se eligió (mostrar todos)."""
    return set(
        CuadroHonorariosColumna.objects.filter(sucursal=sucursal).values_list(
            'vendedor_id', flat=True
        )
    )


def opciones_columnas_vendedores(sucursal):
    """Lista de vendedores activos con el tilde de la planilla."""
    todos = _vendedores_activos_sucursal(sucursal)
    guardados = ids_columnas_vendedores(sucursal)
    hay_filtro = bool(guardados)
    opciones = []
    for v in todos:
        opciones.append({
            'id': v.id,
            'label': _col_label_vendedor(v),
            'nombre': f'{(v.apellido or "").strip()}, {(v.nombre or "").strip()}'.strip(', ') or str(v),
            'checked': (v.id in guardados) if hay_filtro else True,
        })
    return opciones, hay_filtro


def vendedores_para_columnas(sucursal):
    todos = _vendedores_activos_sucursal(sucursal)
    guardados = ids_columnas_vendedores(sucursal)
    if not guardados:
        return todos
    return [v for v in todos if v.id in guardados]


def guardar_columnas_cuadro(sucursal, vendedor_ids):
    """Reemplaza las columnas de productores. Vale para todos los meses."""
    ids = set()
    for raw in vendedor_ids:
        try:
            ids.add(int(raw))
        except (TypeError, ValueError):
            continue
    validos = set(
        Vendedor.objects.filter(
            sucursal=sucursal,
            is_active=True,
            id__in=ids,
        ).values_list('id', flat=True)
    )
    with transaction.atomic():
        CuadroHonorariosColumna.objects.filter(sucursal=sucursal).delete()
        CuadroHonorariosColumna.objects.bulk_create([
            CuadroHonorariosColumna(sucursal=sucursal, vendedor_id=vid)
            for vid in validos
        ])
    return len(validos)


def borrar_columnas_cuadro(sucursal):
    """Vuelve a mostrar todos los productores activos."""
    return CuadroHonorariosColumna.objects.filter(sucursal=sucursal).delete()[0]


def construir_cuadro_honorarios(sucursal, anio, mes):
    """
    Planilla tipo Excel HONORARIOS: columnas OFICINA + personas,
    filas ventas / gestión / fondos / invierno / 24 / día / básico.
    """
    from inmobiliaria.models import OperacionVenta
    from inmobiliaria.oficina_resumen import (
        ETIQUETA_24,
        ETIQUETA_ANIO_INVIERNO,
        ETIQUETA_GESTION_COB,
        ETIQUETA_TEMPORARIOS,
        _honorarios_por_etiqueta,
        _monto_honorarios_etiqueta,
    )

    fecha_desde, fecha_hasta = _rango_mes(anio, mes)
    vendedores_todos = _vendedores_activos_sucursal(sucursal)
    vendedores = vendedores_para_columnas(sucursal)
    fallbacks = {v.id: getattr(v, 'sueldo_basico', None) for v in vendedores}
    basicos = sueldos_basicos_vigentes([v.id for v in vendedores], anio, mes, fallbacks)
    desglose = comisiones_desglose_vendedores(sucursal, fecha_desde, fecha_hasta)
    hon_map, total_fondo, total_cochera = _honorarios_por_etiqueta(
        sucursal, fecha_desde, fecha_hasta
    )

    columnas = [{'key': 'oficina', 'label': 'OFICINA', 'vid': None, 'es_oficina': True, 'basico': None}]
    for v in vendedores:
        columnas.append({
            'key': f'v{v.id}',
            'label': _col_label_vendedor(v),
            'vid': v.id,
            'es_oficina': False,
            'vendedor': v,
            'basico': basicos.get(v.id, _d(0)),
        })
    n = len(columnas)

    ventas = list(
        OperacionVenta.objects.filter(
            sucursal=sucursal,
            estado='confirmada',
            fecha_venta__gte=fecha_desde,
            fecha_venta__lte=fecha_hasta,
        )
        .select_related('propiedad', 'propiedad__propietario', 'vendedor')
        .prefetch_related('vendedores')
        .order_by('fecha_venta', 'id')
    )

    filas = []
    filas.append({'tipo': 'seccion', 'label': 'VENTAS', 'celdas': [None] * n})

    celdas_ventas = []
    for op in ventas:
        celdas = _celdas(n, oficina=op.honorarios_ars)
        filas.append({'tipo': 'dato', 'label': _label_venta(op), 'celdas': celdas})
        celdas_ventas.append(celdas)
    tot_ventas = _sumar_celdas(celdas_ventas, n)
    filas.append({'tipo': 'total', 'label': 'Total:', 'celdas': tot_ventas})
    filas.append({'tipo': 'vacio', 'label': '', 'celdas': [None] * n})

    gestion = _monto_honorarios_etiqueta(hon_map, ETIQUETA_GESTION_COB)
    invierno = _monto_honorarios_etiqueta(hon_map, ETIQUETA_ANIO_INVIERNO)
    meses_24 = _monto_honorarios_etiqueta(hon_map, ETIQUETA_24)
    por_dia = _monto_honorarios_etiqueta(hon_map, ETIQUETA_TEMPORARIOS)

    fila_gestion = _celdas(n, oficina=gestion)
    fila_fondo = _celdas(n, oficina=total_fondo)
    fila_cochera = _celdas(n, oficina=total_cochera)
    fila_tasacion = _celdas(n, oficina=0)
    fila_dif_inv = _celdas(n, oficina=0)
    fila_invierno = _celdas(n, oficina=invierno)
    fila_24 = _celdas(n, oficina=meses_24)
    fila_dia = _celdas(n, oficina=por_dia)

    filas.append({'tipo': 'dato', 'label': 'Comision Gestion Cobranza', 'celdas': fila_gestion})
    filas.append({'tipo': 'dato', 'label': 'Fondo Mantenimiento', 'celdas': fila_fondo})
    filas.append({'tipo': 'dato', 'label': 'Fondo Cochera', 'celdas': fila_cochera})
    filas.append({'tipo': 'vacio', 'label': '', 'celdas': [None] * n})
    filas.append({'tipo': 'dato', 'label': 'Tasacion', 'celdas': fila_tasacion})
    filas.append({'tipo': 'vacio', 'label': '', 'celdas': [None] * n})
    filas.append({'tipo': 'seccion', 'label': 'INVIERNO', 'celdas': [None] * n})
    filas.append({'tipo': 'dato', 'label': 'Diferencias Invierno', 'celdas': fila_dif_inv})
    filas.append({'tipo': 'total', 'label': 'Total Invierno:', 'celdas': fila_invierno})
    filas.append({'tipo': 'dato', 'label': '24 MESES', 'celdas': fila_24})
    filas.append({'tipo': 'dato', 'label': 'POR DÍA', 'celdas': fila_dia})
    filas.append({'tipo': 'vacio', 'label': '', 'celdas': [None] * n})

    tot_honorarios = _sumar_celdas(
        [tot_ventas, fila_gestion, fila_fondo, fila_cochera, fila_tasacion,
         fila_dif_inv, fila_invierno, fila_24, fila_dia],
        n,
    )
    filas.append({'tipo': 'total', 'label': 'TOTAL:', 'celdas': tot_honorarios})

    filas.append({'tipo': 'dato', 'label': 'Diferencia Sueldo', 'celdas': [None] * n})

    celdas_basico = [None] * n
    for i, col in enumerate(columnas):
        if col.get('vid'):
            celdas_basico[i] = basicos.get(col['vid'], _d(0))
    filas.append({
        'tipo': 'basico',
        'label': 'Basico',
        'celdas': celdas_basico,
    })

    por_comis = {}
    for v in vendedores:
        por_comis[v.id] = (desglose.get(v.id) or _desglose_vacio())['total']
    fila_comis = _celdas(n, por_id=por_comis, columnas=columnas)
    filas.append({'tipo': 'dato', 'label': 'Comisiones encargados.', 'celdas': fila_comis})

    tot_final = _sumar_celdas([tot_honorarios, celdas_basico, fila_comis], n)
    filas.append({'tipo': 'total-final', 'label': 'TOTAL.:', 'celdas': tot_final})

    por_comis_todos = {}
    for v in vendedores_todos:
        por_comis_todos[v.id] = (desglose.get(v.id) or _desglose_vacio())['total']

    productores = []
    total_prod = _d(0)
    for v in vendedores_todos:
        comis = por_comis_todos.get(v.id, _d(0))
        if comis == 0:
            continue
        productores.append({
            'nombre': _col_label_vendedor(v),
            'monto': comis,
        })
        total_prod += comis

    return {
        'anio': anio,
        'mes': mes,
        'mes_nombre': MESES_ES[mes] if 1 <= mes <= 12 else '',
        'titulo_mes': f'{MESES_ES[mes]} DE {anio}' if 1 <= mes <= 12 else f'{anio}',
        'columnas': columnas,
        'n_cols': n + 1,
        'filas': filas,
        'productores': productores,
        'productores_total': total_prod,
        'total_gral': tot_final[0] if tot_final else _d(0),
    }
