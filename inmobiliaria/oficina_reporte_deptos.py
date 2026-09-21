"""Reporte mensual de departamentos de oficina (libro por depto).

Regla de saldos (como la planilla en papel):
- ING. NETO del mes = bruto − gastos − arrastre de meses anteriores.
- Si el neto queda negativo: se muestra entre paréntesis, NO suma al total,
  y ese monto se arrastra en contra del mismo depto al mes siguiente.
- Al total del mes solo entran los netos positivos.

Conteo: solo movimientos desde FECHA_INICIO_CONTEO_DEPTOS_OFICINA (8/6/2026).
Lo anterior no entra ni genera arrastre.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

# A partir de esta fecha cuenta el libro / arrastre de departamentos de oficina.
FECHA_INICIO_CONTEO_DEPTOS_OFICINA = date(2026, 6, 8)

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


def _modalidad_ocupacion_mes(prop, anio: int, mes: int) -> str | None:
    """
    Qué tipo de alquiler cubre el mes: 'invierno', '24', 'dia' o None.
    Prioridad: contrato invierno / 24 meses vigente; si no, operaciones por día.
    """
    from inmobiliaria.models import ContratoAlquiler, Reserva

    inicio = date(anio, mes, 1)
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])

    contratos = (
        ContratoAlquiler.objects.filter(
            propiedad_id=prop.id,
            fecha_inicio__lte=fin,
            fecha_fin__gte=inicio,
        )
        .exclude(estado='rescindido')
        .order_by('-fecha_inicio', '-id')
    )
    for c in contratos:
        try:
            cat = c.categoria_tipo_operacion()
        except Exception:
            cat = None
        dur = int(getattr(c, 'duracion_meses', 0) or 0)
        if cat == 'invierno' or dur == 9:
            return 'invierno'
        if cat in ('24', '6') or dur >= 12:
            return '24'

    # Sin contrato largo: ¿hubo reserva/operación por día que toque el mes?
    hay_dia = (
        Reserva.objects.filter(
            propiedad_id=prop.id,
            fecha_inicio__lte=fin,
            fecha_fin__gte=inicio,
            eliminada=False,
        )
        .exclude(estado='cancelada')
        .exists()
    )
    if hay_dia:
        return 'dia'
    return None


_ESTADOS_LIQUIDACION_ALQUILERES_PROPIOS = ('oficina', 'pagada', 'cerrada', 'procesada')


def _modalidad_desde_liquidacion(liq) -> str | None:
    """Clasifica una liquidación: día (reserva), invierno o 24 (contrato)."""
    if getattr(liq, 'reserva_id', None):
        return 'dia'
    contrato = getattr(liq, 'contrato', None)
    if contrato is None:
        return None
    try:
        cat = contrato.categoria_tipo_operacion()
    except Exception:
        cat = None
    dur = int(getattr(contrato, 'duracion_meses', 0) or 0)
    if cat == 'invierno' or dur == 9:
        return 'invierno'
    if cat in ('24', '6') or dur >= 12:
        return '24'
    return None


def _monto_ars_liquidacion_propietario(liq) -> Decimal:
    """Monto del depto/propietario en ARS (como en el libro)."""
    monto = Decimal(str(getattr(liq, 'monto_propietario', None) or 0))
    if monto <= 0:
        monto = Decimal(str(getattr(liq, 'monto_a_pagar', None) or 0))
    if monto <= 0:
        return Decimal('0')
    moneda = (getattr(liq, 'moneda', None) or 'ARS').strip().upper()
    if moneda != 'USD':
        return _q(monto)
    cotiz = getattr(liq, 'cotizacion_dolar', None)
    if cotiz is not None:
        cotiz = Decimal(str(cotiz))
        if cotiz > 0:
            return _q(monto * cotiz)
    return Decimal('0')


def _fecha_periodo_liquidacion(liq):
    """Fecha de período de la liquidación (misma regla que el libro del depto)."""
    fecha_raw = (
        getattr(liq, 'fecha_desde', None)
        or getattr(liq, 'fecha_procesamiento', None)
        or getattr(liq, 'fecha_creacion', None)
    )
    return _fecha_sola(fecha_raw)


def _vacios_modalidad():
    return {'por_dia': None, 'invierno': None, 'meses_24': None}


def _acumular_liquidacion_en_tarifas(tarifas: dict, liq) -> None:
    f_date = _fecha_periodo_liquidacion(liq)
    if f_date is None:
        return
    monto = _monto_ars_liquidacion_propietario(liq)
    if monto <= Decimal('0.009'):
        return
    mod = _modalidad_desde_liquidacion(liq)
    if mod == 'dia':
        tarifas['por_dia'] = _q((tarifas['por_dia'] or Decimal('0')) + monto)
    elif mod == 'invierno':
        tarifas['invierno'] = _q((tarifas['invierno'] or Decimal('0')) + monto)
    elif mod == '24':
        tarifas['meses_24'] = _q((tarifas['meses_24'] or Decimal('0')) + monto)


def mapa_ingresos_liquidaciones_por_modalidad(propiedad_ids, anio: int, mes: int, sucursal=None):
    """
    {propiedad_id: {por_dia, invierno, meses_24}} solo con liquidaciones
    confirmadas del mes. Keys con monto 0 quedan en None.
    """
    # Propiedad.id es CharField: no castear a int.
    ids = [str(x) for x in propiedad_ids if x is not None and str(x).strip() != '']
    resultado = {pid: _vacios_modalidad() for pid in ids}
    if not ids:
        return resultado

    from inmobiliaria.models import LiquidacionPropietario

    inicio = date(anio, mes, 1)
    fin = date(anio, mes, calendar.monthrange(anio, mes)[1])

    qs = (
        LiquidacionPropietario.objects.filter(
            propiedad_id__in=ids,
            estado__in=_ESTADOS_LIQUIDACION_ALQUILERES_PROPIOS,
        )
        .exclude(reserva__eliminada=True)
        .exclude(reserva__estado='cancelada')
        .exclude(contrato__estado='rescindido')
        .select_related('contrato', 'reserva')
    )
    if sucursal is not None:
        qs = qs.filter(sucursal=sucursal)

    for liq in qs.iterator(chunk_size=500):
        f_date = _fecha_periodo_liquidacion(liq)
        if f_date is None or f_date < inicio or f_date > fin:
            continue
        pid = str(liq.propiedad_id)
        if pid not in resultado:
            continue
        _acumular_liquidacion_en_tarifas(resultado[pid], liq)

    return resultado


def ingresos_realizados_por_modalidad(prop, anio: int, mes: int, bruto_mes=None) -> dict:
    """
    Alquileres propios del mes por modalidad (día / invierno / 24).

    Solo cuenta liquidaciones confirmadas (oficina/pagada/cerrada/procesada)
    del período. Sin liquidación → cero. No usa el bruto del libro ni tarifas
    de ficha (evita inflar «por día» con otros ingresos de caja).
    """
    prop_id = getattr(prop, 'id', None) or prop
    if prop_id is None or str(prop_id).strip() == '':
        return _vacios_modalidad()
    prop_id = str(prop_id)
    sucursal = getattr(prop, 'sucursal', None)
    return mapa_ingresos_liquidaciones_por_modalidad(
        [prop_id], anio, mes, sucursal=sucursal
    ).get(prop_id, _vacios_modalidad())


def preferencias_reporte_deptos(sucursal):
    """Devuelve sets de ids ocultos y forzados para el resumen."""
    from inmobiliaria.models import ReporteDeptosOficinaPreferencia

    ocultos = set()
    forzados = set()
    for row in ReporteDeptosOficinaPreferencia.objects.filter(sucursal=sucursal).only(
        'propiedad_id', 'oculto', 'forzado'
    ):
        if row.oculto:
            ocultos.add(row.propiedad_id)
        if row.forzado:
            forzados.add(row.propiedad_id)
    return ocultos, forzados


def _filas_libro_sin_inicio(sucursal, propiedad, dr_desde, dr_hasta):
    """
    Filas del libro en el rango (sin fila de inicio de caja).
    Reutiliza la misma lógica que la pantalla del libro.
    """
    from inmobiliaria.models import CotizacionLibroOperacion, Reserva
    from inmobiliaria.views_oficina import (
        _filas_contratos_faltantes_libro,
        _filas_liquidaciones_oficina_libro,
        _filas_operaciones_faltantes_libro,
        _fila_libro_desde_movimiento,
        _liquidaciones_por_reserva,
        _monto_propietario_reserva_libro,
        _obtener_inicio_caja_libro,
        _qs_movimientos_libro_propiedad,
    )

    inicio = _obtener_inicio_caja_libro(propiedad)
    fecha_corte = getattr(inicio, 'fecha', None)
    # Piso global: nada anterior al 8/6/2026
    if fecha_corte is None or fecha_corte < FECHA_INICIO_CONTEO_DEPTOS_OFICINA:
        fecha_corte = FECHA_INICIO_CONTEO_DEPTOS_OFICINA
    if dr_desde is None or dr_desde < fecha_corte:
        dr_desde = fecha_corte

    movimientos, reserva_ids, contrato_ids = _qs_movimientos_libro_propiedad(
        sucursal, propiedad, dr_desde=dr_desde, dr_hasta=dr_hasta
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
    Respeta preferencias: ocultos no salen; forzados salen aunque estén en cero.
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

    ocultos, forzados = preferencias_reporte_deptos(sucursal)

    props = _ordenar_propiedades_oficina(
        list(
            _qs_propiedades_oficina(sucursal)
            .select_related('info_invierno', 'info_meses')
            .prefetch_related('precios')
        ),
        orden='direccion',
    )

    tarifas_por_prop = mapa_ingresos_liquidaciones_por_modalidad(
        [p.id for p in props], anio, mes, sucursal=sucursal
    )
    total_tarifa_dia = Decimal('0')
    total_tarifa_invierno = Decimal('0')
    total_tarifa_24 = Decimal('0')
    for pid, tarifas in tarifas_por_prop.items():
        if pid in ocultos:
            continue
        if tarifas.get('por_dia'):
            total_tarifa_dia += tarifas['por_dia']
        if tarifas.get('invierno'):
            total_tarifa_invierno += tarifas['invierno']
        if tarifas.get('meses_24'):
            total_tarifa_24 += tarifas['meses_24']

    filas = []
    ocultos_labels = []
    disponibles_para_agregar = []
    total_bruto = Decimal('0')
    total_gastos = Decimal('0')
    total_neto_positivos = Decimal('0')
    n_positivos = 0
    n_negativos = 0

    for prop in props:
        label = etiqueta_propiedad_oficina(prop)
        if prop.id in ocultos:
            ocultos_labels.append({'id': prop.id, 'label': label})
            continue

        # Desde el 8/6/2026 (o inicio de caja si es posterior) hasta fin del mes pedido
        filas_libro, fecha_corte = _filas_libro_sin_inicio(
            sucursal, prop,
            dr_desde=FECHA_INICIO_CONTEO_DEPTOS_OFICINA,
            dr_hasta=fecha_hasta,
        )
        buckets = _buckets_mensuales(filas_libro)
        calc = _aplicar_arrastre(buckets, anio, mes, fecha_corte=fecha_corte)

        # Omitir deptos sin movimiento ni arrastre en el mes (todo en cero),
        # salvo que estén forzados a aparecer.
        sin_mov = (
            calc['bruto'] <= Decimal('0.009')
            and calc['gastos'] <= Decimal('0.009')
            and calc['arrastre_anterior'] <= Decimal('0.009')
            and abs(calc['neto']) <= Decimal('0.009')
        )
        if sin_mov and prop.id not in forzados:
            disponibles_para_agregar.append({'id': prop.id, 'label': label})
            continue

        total_bruto += calc['bruto']
        total_gastos += calc['gastos']
        if calc['entra_en_total']:
            total_neto_positivos += calc['monto_a_total']
            n_positivos += 1
        elif calc['negativo']:
            n_negativos += 1

        tarifas = tarifas_por_prop.get(prop.id) or _vacios_modalidad()
        filas.append({
            'nro': len(filas) + 1,
            'propiedad': prop,
            'propiedad_label': label,
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
            'tarifa_por_dia': tarifas['por_dia'],
            'tarifa_invierno': tarifas['invierno'],
            'tarifa_24_meses': tarifas['meses_24'],
            'forzado': prop.id in forzados,
        })

    # Renumerar tras filtrar vacíos
    for i, f in enumerate(filas, start=1):
        f['nro'] = i

    # Ocultos también pueden “agregarse” de nuevo
    disponibles_para_agregar = ocultos_labels + disponibles_para_agregar
    disponibles_para_agregar.sort(key=lambda x: x['label'].lower())

    return {
        'anio': anio,
        'mes': mes,
        'periodo_label': periodo_label,
        'filas': filas,
        'total_bruto': _q(total_bruto),
        'total_gastos': _q(total_gastos),
        'total_neto': _q(total_neto_positivos),
        'total_tarifa_dia': _q(total_tarifa_dia),
        'total_tarifa_invierno': _q(total_tarifa_invierno),
        'total_tarifa_24': _q(total_tarifa_24),
        'n_positivos': n_positivos,
        'n_negativos': n_negativos,
        'cantidad': len(filas),
        'fecha_inicio_conteo': FECHA_INICIO_CONTEO_DEPTOS_OFICINA,
        'ocultos': ocultos_labels,
        'disponibles_para_agregar': disponibles_para_agregar,
    }
