"""Reporte mensual de departamentos de oficina (libro por depto).

Regla de saldos (como la planilla en papel):
- ING. NETO del mes = bruto − gastos − arrastre de meses anteriores.
- Si el neto queda negativo: se muestra entre paréntesis, NO suma al total,
  y ese monto se arrastra en contra del mismo depto al mes siguiente.
- Al total del mes solo entran los netos positivos.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

MESES_ES = (
    '',
    'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
    'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE',
)


def _q(n) -> Decimal:
    return Decimal(str(n or 0)).quantize(Decimal('0.01'))


def _fecha_sola(valor):
    if not valor:
        return None
    if isinstance(valor, datetime):
        try:
            if timezone.is_aware(valor):
                return timezone.localtime(valor).date()
        except Exception:
            pass
        return valor.date()
    if isinstance(valor, date):
        return valor
    if hasattr(valor, 'date'):
        try:
            return valor.date()
        except Exception:
            return None
    return None


def etiqueta_propiedad_oficina(prop) -> str:
    """Etiqueta tipo planilla: dirección + piso/depto."""
    partes = [(prop.direccion or '').strip()]
    piso = (getattr(prop, 'piso', None) or '').strip()
    depto = (getattr(prop, 'departamento', None) or '').strip()
    if piso or depto:
        extra = ' '.join(x for x in (piso, depto) if x)
        if extra:
            partes.append(extra)
    label = ' — '.join(p for p in partes if p)
    return label or f'#{prop.id}'


def _filas_libro_sin_inicio(sucursal, propiedad, dr_desde, dr_hasta):
    """
    Filas del libro en el rango (sin fila de inicio de caja).
    Reutiliza la misma lógica que la pantalla del libro.
    """
    from inmobiliaria.models import CotizacionLibroOperacion, Reserva
    from inmobiliaria.views_oficina import (
        _ESTADOS_LIQUIDACION_LIBRO,
        _contexto_exclusion_operaciones_libro,
        _cotizaciones_movimientos_por_reserva,
        _filas_contratos_faltantes_libro,
        _filas_liquidaciones_oficina_libro,
        _filas_operaciones_faltantes_libro,
        _fila_libro_desde_movimiento,
        _liquidaciones_por_reserva,
        _monto_propietario_reserva_libro,
        _obtener_inicio_caja_libro,
        _qs_movimientos_libro_propiedad,
    )
    from inmobiliaria.models import LiquidacionPropietario

    inicio = _obtener_inicio_caja_libro(propiedad)
    fecha_corte = getattr(inicio, 'fecha', None)
    if fecha_corte and (dr_desde is None or dr_desde < fecha_corte):
        dr_desde = fecha_corte

    reservas_anuladas, contratos_rescindidos = _contexto_exclusion_operaciones_libro(
        propiedad, sucursal
    )

    movimientos, reserva_ids, contrato_ids = _qs_movimientos_libro_propiedad(
        sucursal,
        propiedad,
        dr_desde=dr_desde,
        dr_hasta=dr_hasta,
        reservas_anuladas=reservas_anuladas,
        contratos_rescindidos=contratos_rescindidos,
    )

    liq_por_reserva = _liquidaciones_por_reserva(reserva_ids)
    cotiz_por_reserva = {}
    if reserva_ids:
        for row in CotizacionLibroOperacion.objects.filter(reserva_id__in=reserva_ids).values(
            'reserva_id', 'cotizacion_dolar'
        ):
            cotiz_por_reserva[row['reserva_id']] = row['cotizacion_dolar']

    monto_prop_por_reserva = {}
    if reserva_ids:
        for r in Reserva.objects.filter(id__in=reserva_ids).only(
            'id',
            'precio_total',
            'moneda',
            'liq_monto_propietario',
            'liq_monto_inmobiliaria',
            'liq_monto_cochera',
            'liq_monto_fondo',
            'propiedad_id',
            'fecha_inicio',
            'fecha_fin',
            'sucursal_id',
        ):
            mp = _monto_propietario_reserva_libro(r, liq_por_reserva.get(r.id))
            monto_prop_por_reserva[r.id] = mp
            monto_prop_por_reserva[f'_total_{r.id}'] = Decimal(str(r.precio_total or 0))

    liq_reserva_ids = list(
        LiquidacionPropietario.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
            estado__in=_ESTADOS_LIQUIDACION_LIBRO,
            reserva_id__isnull=False,
        )
        .exclude(reserva_id__in=reservas_anuladas)
        .values_list('reserva_id', flat=True)
        .distinct()
    )
    ids_cotiz = sorted(set(reserva_ids) | set(liq_reserva_ids))
    cotiz_mov_por_reserva = (
        _cotizaciones_movimientos_por_reserva(sucursal, ids_cotiz) if ids_cotiz else {}
    )

    filas = [
        f
        for f in (
            _fila_libro_desde_movimiento(
                m,
                monto_prop_por_reserva=monto_prop_por_reserva,
                cotiz_por_reserva=cotiz_por_reserva,
            )
            for m in movimientos
        )
        if f is not None
    ]
    filas.extend(
        _filas_operaciones_faltantes_libro(
            propiedad,
            sucursal,
            reserva_ids,
            movimientos,
            dr_desde=dr_desde,
            dr_hasta=dr_hasta,
            liq_por_reserva=liq_por_reserva,
            cotiz_por_reserva=cotiz_por_reserva,
        )
    )
    filas.extend(
        _filas_contratos_faltantes_libro(
            propiedad,
            sucursal,
            contrato_ids,
            movimientos,
            dr_desde=dr_desde,
            dr_hasta=dr_hasta,
        )
    )
    filas.extend(
        _filas_liquidaciones_oficina_libro(
            propiedad,
            sucursal,
            movimientos=movimientos,
            dr_desde=dr_desde,
            dr_hasta=dr_hasta,
            cotiz_por_reserva=cotiz_por_reserva,
            cotiz_mov_por_reserva=cotiz_mov_por_reserva,
            reservas_anuladas=reservas_anuladas,
            contratos_rescindidos=contratos_rescindidos,
        )
    )

    if fecha_corte:
        filas = [
            f for f in filas
            if (d := _fecha_sola(f.get('fecha'))) is None or d >= fecha_corte
        ]

    # Excluir inicio de caja / marcas especiales
    filas = [
        f for f in filas
        if not f.get('es_inicio_caja')
    ]
    return filas, fecha_corte


def _buckets_mensuales(filas):
    """(anio, mes) → {bruto, gastos} en ARS."""
    buckets = defaultdict(lambda: {'bruto': Decimal('0'), 'gastos': Decimal('0')})
    for f in filas:
        d = _fecha_sola(f.get('fecha'))
        if not d:
            continue
        key = (d.year, d.month)
        buckets[key]['bruto'] += _q(f.get('alquileres_ars'))
        buckets[key]['gastos'] += _q(f.get('gastos_ars'))
    return buckets


def _meses_entre(desde: date, hasta: date):
    """Genera (anio, mes) desde el mes de `desde` hasta el de `hasta` inclusive."""
    y, m = desde.year, desde.month
    y2, m2 = hasta.year, hasta.month
    while (y, m) <= (y2, m2):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


def _aplicar_arrastre(buckets, anio, mes, fecha_corte=None):
    """
    Recorre meses hasta (anio, mes) aplicando arrastre de negativos.
    Devuelve dict del mes pedido + arrastre_siguiente.
    """
    if fecha_corte:
        start = date(fecha_corte.year, fecha_corte.month, 1)
    else:
        if not buckets:
            start = date(anio, mes, 1)
        else:
            y0, m0 = min(buckets.keys())
            start = date(y0, m0, 1)

    fin = date(anio, mes, 1)
    if start > fin:
        start = fin

    arrastre = Decimal('0')
    resultado_mes = None

    for y, m in _meses_entre(start, fin):
        b = buckets.get((y, m), {'bruto': Decimal('0'), 'gastos': Decimal('0')})
        bruto = _q(b['bruto'])
        gastos = _q(b['gastos'])
        neto_periodo = _q(bruto - gastos)
        neto_ajustado = _q(neto_periodo - arrastre)
        arrastre_aplicado = arrastre

        if neto_ajustado < 0:
            entra_en_total = False
            monto_a_total = Decimal('0')
            arrastre = _q(-neto_ajustado)
        else:
            entra_en_total = neto_ajustado > Decimal('0.009')
            monto_a_total = neto_ajustado if entra_en_total else Decimal('0')
            arrastre = Decimal('0')

        if (y, m) == (anio, mes):
            resultado_mes = {
                'bruto': bruto,
                'gastos': gastos,
                'neto_periodo': neto_periodo,
                'arrastre_anterior': arrastre_aplicado,
                'neto': neto_ajustado,
                'negativo': neto_ajustado < 0,
                'entra_en_total': entra_en_total,
                'monto_a_total': monto_a_total,
                'arrastre_siguiente': arrastre,
            }

    if resultado_mes is None:
        resultado_mes = {
            'bruto': Decimal('0'),
            'gastos': Decimal('0'),
            'neto_periodo': Decimal('0'),
            'arrastre_anterior': Decimal('0'),
            'neto': Decimal('0'),
            'negativo': False,
            'entra_en_total': False,
            'monto_a_total': Decimal('0'),
            'arrastre_siguiente': Decimal('0'),
        }
    return resultado_mes


def construir_reporte_mensual_deptos_oficina(sucursal, anio: int, mes: int):
    """
    Arma el reporte mensual de todos los deptos de la cartera de oficina.
    """
    from inmobiliaria.views_oficina import (
        _ordenar_propiedades_oficina,
        _qs_propiedades_oficina,
    )

    anio = int(anio)
    mes = int(mes)
    ultimo_dia = calendar.monthrange(anio, mes)[1]
    fecha_hasta = date(anio, mes, ultimo_dia)
    periodo_label = f'{MESES_ES[mes]} DE {anio}'

    props = _ordenar_propiedades_oficina(
        list(_qs_propiedades_oficina(sucursal)),
        orden='piso',
    )

    filas = []
    total_bruto = Decimal('0')
    total_gastos = Decimal('0')
    total_neto_positivos = Decimal('0')
    n_positivos = 0
    n_negativos = 0

    for prop in props:
        # Traer desde un piso amplio: inicio de caja hasta fin del mes pedido
        filas_libro, fecha_corte = _filas_libro_sin_inicio(
            sucursal, prop, dr_desde=None, dr_hasta=fecha_hasta
        )
        buckets = _buckets_mensuales(filas_libro)
        calc = _aplicar_arrastre(buckets, anio, mes, fecha_corte=fecha_corte)

        # Omitir deptos sin movimiento ni arrastre en el mes (todo en cero)
        sin_mov = (
            calc['bruto'] <= Decimal('0.009')
            and calc['gastos'] <= Decimal('0.009')
            and calc['arrastre_anterior'] <= Decimal('0.009')
            and abs(calc['neto']) <= Decimal('0.009')
        )
        if sin_mov:
            continue

        total_bruto += calc['bruto']
        total_gastos += calc['gastos']
        if calc['entra_en_total']:
            total_neto_positivos += calc['monto_a_total']
            n_positivos += 1
        elif calc['negativo']:
            n_negativos += 1

        filas.append({
            'nro': len(filas) + 1,
            'propiedad': prop,
            'propiedad_label': etiqueta_propiedad_oficina(prop),
            'periodo': periodo_label,
            'bruto': calc['bruto'],
            'gastos': calc['gastos'],
            'neto': calc['neto'],
            'neto_abs': _q(abs(calc['neto'])),
            'neto_periodo': calc['neto_periodo'],
            'arrastre_anterior': calc['arrastre_anterior'],
            'negativo': calc['negativo'],
            'entra_en_total': calc['entra_en_total'],
            'arrastre_siguiente': calc['arrastre_siguiente'],
            'fecha_desde_mes': date(anio, mes, 1).isoformat(),
            'fecha_hasta_mes': fecha_hasta.isoformat(),
        })

    # Renumerar tras filtrar vacíos
    for i, f in enumerate(filas, start=1):
        f['nro'] = i

    return {
        'anio': anio,
        'mes': mes,
        'periodo_label': periodo_label,
        'filas': filas,
        'total_bruto': _q(total_bruto),
        'total_gastos': _q(total_gastos),
        'total_neto': _q(total_neto_positivos),
        'n_positivos': n_positivos,
        'n_negativos': n_negativos,
        'cantidad': len(filas),
    }
