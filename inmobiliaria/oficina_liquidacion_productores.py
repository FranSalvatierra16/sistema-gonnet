"""Liquidación mensual de productores: sueldo básico + comisiones."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.db import transaction

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models import ComisionVendedor, SueldoBasicoVigencia, Vendedor
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
