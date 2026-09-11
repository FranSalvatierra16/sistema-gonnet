"""Liquidación mensual de productores: sueldo básico + comisiones."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import unicodedata

from django.db import transaction
from django.db.models import Q, Sum

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models import (
    CategoriaGastoOficina,
    ComisionVendedor,
    CuadroHonorariosColumna,
    CuadroHonorariosTotalGral,
    GastoOficina,
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
    """Misma clasificación que el historial: día / invierno / 24 / venta."""
    cat, _sub = comision.clasificacion_listado()
    if cat in ('por_dia', 'por_invierno', 'por_24_meses', 'por_venta'):
        return cat
    if cat == 'operacion':
        return 'otros'
    return 'honorarios'


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
    nom = (v.nombre or '').strip()
    if nom:
        return nom.split()[0].upper()
    return ((v.apellido or '').strip().upper() or f'#{v.id}')


def _label_venta(op):
    nombre = (getattr(op, 'propiedad_nombre', None) or '').strip()
    if not nombre:
        prop = getattr(op, 'propiedad', None)
        if prop is not None:
            dueño = getattr(prop, 'propietario', None)
            if dueño:
                nombre = (
                    getattr(dueño, 'apellido', None) or getattr(dueño, 'nombre', None) or ''
                ).strip()
            if not nombre:
                nombre = (getattr(prop, 'direccion', None) or '').strip()
    comprador = (getattr(op, 'comprador_nombre', None) or '').strip()
    if nombre and comprador:
        return f'{nombre} - {comprador}'
    return comprador or nombre or f'Venta #{op.id}'


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


def _montos_desglose(desglose, clave):
    out = {}
    for vid, row in desglose.items():
        monto = _d(row.get(clave))
        if monto != 0:
            out[vid] = monto
    return out


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


def _norm_tokens_nombre(texto):
    t = unicodedata.normalize('NFD', (texto or '').lower())
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = ''.join(c if c.isalnum() else ' ' for c in t)
    return tuple(p for p in t.split() if p)


def _distancia_edicion(a, b):
    """Levenshtein simple (nombres cortos)."""
    a = a or ''
    b = b or ''
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(min(
                prev[j] + 1,
                cur[j - 1] + 1,
                prev[j - 1] + (0 if ca == cb else 1),
            ))
        prev = cur
    return prev[-1]


def _nombres_sueldo_compatibles(nombre_a, nombre_b):
    """True si son el mismo nombre (permite typo tipo Kucic/Kucik)."""
    ta = _norm_tokens_nombre(nombre_a)
    tb = _norm_tokens_nombre(nombre_b)
    if not ta or not tb or len(ta) != len(tb):
        return False
    if set(ta) == set(tb):
        return True
    usados = [False] * len(tb)
    for tok_a in ta:
        hallado = False
        for i, tok_b in enumerate(tb):
            if usados[i]:
                continue
            if tok_a == tok_b or _distancia_edicion(tok_a, tok_b) <= 1:
                usados[i] = True
                hallado = True
                break
        if not hallado:
            return False
    return True


def _match_vendedor_por_nombre(nombre_cat, vendedores):
    tokens = set(_norm_tokens_nombre(nombre_cat))
    if not tokens:
        return None
    hits = []
    for v in vendedores:
        vt = set(_norm_tokens_nombre(v.apellido) + _norm_tokens_nombre(v.nombre))
        if vt and (vt == tokens or _nombres_sueldo_compatibles(nombre_cat, f'{v.apellido} {v.nombre}')):
            hits.append(v)
    if len(hits) == 1:
        return hits[0]
    return None


def _montos_sueldos_pagados(sucursal, fecha_desde, fecha_hasta):
    """
    Sueldos efectivamente pagados en el mes (GastoOficina › Sueldos).
    Ignora montos 0 del reparto Colón/Corrientes.
    """
    qs = (
        GastoOficina.objects.filter(
            sucursal=sucursal,
            fecha__gte=fecha_desde,
            fecha__lte=fecha_hasta,
        )
        .filter(
            Q(categoria__parent__nombre__iexact='Sueldos')
            | Q(categoria__nombre__iexact='Sueldos')
        )
        .select_related('categoria', 'vendedor')
    )
    lineas = []
    for g in qs:
        monto = abs(_d(g.monto))
        if monto <= 0:
            continue
        v = g.vendedor
        nombre_v = ''
        if v:
            nombre_v = (
                f'{(v.apellido or "").strip()}, {(v.nombre or "").strip()}'.strip(' ,')
            )
        lineas.append({
            'id': g.id,
            'cid': g.categoria_id,
            'vid': g.vendedor_id,
            'nombre_cat': (g.categoria.nombre or '').strip() if g.categoria_id else '',
            'nombre_vend': nombre_v,
            'monto': monto,
        })
    return lineas


def _monto_sueldo_para_fila(fsg, lineas):
    """Resuelve el sueldo pagado de una fila TOTAL GRAL (sin duplicar)."""
    cid = fsg.get('cid')
    vid = fsg.get('vid')
    nombre = (fsg.get('nombre') or '').strip()
    total = _d(0)
    vistos = set()
    for lin in lineas:
        if lin['id'] in vistos:
            continue
        ok = False
        if cid and lin['cid'] == cid:
            ok = True
        elif vid and lin['vid'] == vid:
            ok = True
        elif nombre and (
            _nombres_sueldo_compatibles(nombre, lin['nombre_cat'])
            or _nombres_sueldo_compatibles(nombre, lin['nombre_vend'])
        ):
            ok = True
        if ok:
            vistos.add(lin['id'])
            total += lin['monto']
    return total


def filas_sueldos(sucursal):
    """
    Todas las filas activas de Categorías › Sueldos (con o sin badge vendedor).
    Couñago Ruben y otras cargadas a mano también entran.
    """
    from inmobiliaria.oficina_gastos import SUBCATEGORIAS_LEGACY_SUELDOS

    hijos = (
        CategoriaGastoOficina.objects.filter(
            sucursal=sucursal,
            parent__isnull=False,
            parent__parent__isnull=True,
            parent__nombre__iexact='Sueldos',
            activa=True,
        )
        .select_related('vendedor')
        .order_by('orden', 'nombre', 'id')
    )
    vendedores_suc = list(
        Vendedor.objects.filter(sucursal=sucursal).only('id', 'nombre', 'apellido')
    )
    filas = []
    vistos_vid = set()
    for hijo in hijos:
        nom = (hijo.nombre or '').strip()
        if not nom or nom.casefold() in SUBCATEGORIAS_LEGACY_SUELDOS:
            continue
        v = hijo.vendedor
        if not v:
            v = _match_vendedor_por_nombre(nom, vendedores_suc)
        if v and v.id in vistos_vid:
            continue
        if v:
            vistos_vid.add(v.id)
            key = f'v-{v.id}'
        else:
            key = f'c-{hijo.id}'
        filas.append({
            'key': key,
            'vid': v.id if v else None,
            'cid': hijo.id,
            'nombre': nom,
            'vendedor': v,
        })
    return filas


def vendedores_en_sueldos(sucursal):
    """Productores de Sueldos que sí tienen usuario vendedor (para columnas)."""
    out = []
    vistos = set()
    for fila in filas_sueldos(sucursal):
        v = fila.get('vendedor')
        if not v or v.id in vistos:
            continue
        vistos.add(v.id)
        out.append(v)
    return out or _vendedores_activos_sucursal(sucursal)


def ids_columnas_vendedores(sucursal):
    """IDs guardados para la planilla. Set vacío = todavía no se eligió (mostrar todos)."""
    return set(
        CuadroHonorariosColumna.objects.filter(sucursal=sucursal).values_list(
            'vendedor_id', flat=True
        )
    )


def opciones_columnas_vendedores(sucursal):
    """Lista de vendedores de Sueldos con el tilde de la planilla."""
    todos = vendedores_en_sueldos(sucursal)
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
    todos = vendedores_en_sueldos(sucursal)
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
    permitidos = {v.id for v in vendedores_en_sueldos(sucursal)}
    validos = {vid for vid in ids if vid in permitidos}
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


def ids_total_gral(sucursal):
    """Claves marcadas: 'v-12' (vendedor) o 'c-34' (categoría de Sueldos)."""
    keys = set()
    for row in CuadroHonorariosTotalGral.objects.filter(sucursal=sucursal).only(
        'vendedor_id', 'categoria_id'
    ):
        if row.vendedor_id:
            keys.add(f'v-{row.vendedor_id}')
        elif row.categoria_id:
            keys.add(f'c-{row.categoria_id}')
    return keys


def _parse_clave_total_gral(raw):
    texto = str(raw or '').strip()
    if not texto:
        return None
    if texto.isdigit():
        return f'v-{int(texto)}'
    if texto.startswith('v-') or texto.startswith('c-'):
        return texto
    return None


def guardar_total_gral(sucursal, vendedor_ids):
    """Reemplaza quién entra en TOTAL GRAL. Vale para todos los meses."""
    filas_por_key = {f['key']: f for f in filas_sueldos(sucursal)}
    elegidas = []
    vistos = set()
    for raw in vendedor_ids:
        key = _parse_clave_total_gral(raw)
        fila = filas_por_key.get(key) if key else None
        if not fila or fila['key'] in vistos:
            continue
        vistos.add(fila['key'])
        elegidas.append(fila)
    with transaction.atomic():
        CuadroHonorariosTotalGral.objects.filter(sucursal=sucursal).delete()
        CuadroHonorariosTotalGral.objects.bulk_create([
            CuadroHonorariosTotalGral(
                sucursal=sucursal,
                vendedor_id=fila['vid'],
                categoria_id=None if fila['vid'] else fila['cid'],
            )
            for fila in elegidas
        ])
    return len(elegidas)


def borrar_total_gral(sucursal):
    return CuadroHonorariosTotalGral.objects.filter(sucursal=sucursal).delete()[0]


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
    vendedores_sueldos = vendedores_en_sueldos(sucursal)
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
    por_venta_prod = _montos_desglose(desglose, 'por_venta')
    for i, col in enumerate(columnas):
        vid = col.get('vid')
        if not vid:
            continue
        monto = por_venta_prod.get(vid)
        tot_ventas[i] = monto if monto is not None else None
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
    fila_invierno = _celdas(
        n, oficina=invierno,
        por_id=_montos_desglose(desglose, 'por_invierno'),
        columnas=columnas,
    )
    fila_24 = _celdas(
        n, oficina=meses_24,
        por_id=_montos_desglose(desglose, 'por_24_meses'),
        columnas=columnas,
    )
    fila_dia = _celdas(
        n, oficina=por_dia,
        por_id=_montos_desglose(desglose, 'por_dia'),
        columnas=columnas,
    )

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

    por_resto = {}
    for v in vendedores:
        d = desglose.get(v.id) or _desglose_vacio()
        resto = _d(d['honorarios']) + _d(d['otros'])
        if resto != 0:
            por_resto[v.id] = resto
    fila_comis = _celdas(n, por_id=por_resto, columnas=columnas)
    filas.append({'tipo': 'dato', 'label': 'Comisiones encargados.', 'celdas': fila_comis})

    tot_final = _sumar_celdas([tot_honorarios, celdas_basico, fila_comis], n)
    filas.append({'tipo': 'total-final', 'label': 'TOTAL.:', 'celdas': tot_final})

    filas_sg = filas_sueldos(sucursal)
    lineas_sueldo = _montos_sueldos_pagados(sucursal, fecha_desde, fecha_hasta)

    guardados_total = ids_total_gral(sucursal)
    hay_filtro_total = bool(guardados_total)

    productores = []
    total_prod = _d(0)
    for fsg in filas_sg:
        # Monto = sueldo pagado en Gastos de oficina › Sueldos del mes.
        monto = _monto_sueldo_para_fila(fsg, lineas_sueldo)
        if hay_filtro_total:
            checked = fsg['key'] in guardados_total
        else:
            checked = monto != 0
        productores.append({
            'id': fsg['key'],
            'key': fsg['key'],
            'nombre': fsg['nombre'],
            'monto': monto,
            'checked': checked,
        })
        if checked:
            total_prod += monto

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
        'productores_filtrados': hay_filtro_total,
        'total_gral': tot_final[0] if tot_final else _d(0),
    }
