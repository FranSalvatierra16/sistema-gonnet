"""
Helpers de rendimiento para buscar_propiedades (reservas/nuevo).
Evita N+1: precios en memoria, reservas/disponibilidades/contratos precargados.
"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Max, Min, Q


def tipo_precio_para_dia_reserva(dia_a_usar):
    if dia_a_usar.month == 1:
        return 'QUINCENA_1_ENERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_ENERO'
    if dia_a_usar.month == 2:
        return 'QUINCENA_1_FEBRERO' if dia_a_usar.day <= 15 else 'QUINCENA_2_FEBRERO'
    if dia_a_usar.month == 3:
        return 'QUINCENA_1_MARZO' if dia_a_usar.day <= 15 else 'QUINCENA_2_MARZO'
    if dia_a_usar.month == 7:
        return 'VACACIONES_INVIERNO'
    if dia_a_usar.month == 12:
        return 'QUINCENA_1_DICIEMBRE' if dia_a_usar.day <= 15 else 'QUINCENA_2_DICIEMBRE'
    return 'TEMPORADA_BAJA'


def mapa_precios_propiedad(propiedad):
    precios = getattr(propiedad, 'todos_precios', None)
    if precios is None:
        precios = propiedad.precios.all()
    return {p.tipo_precio: p for p in precios}


def precio_dia_desde_obj(precio_obj):
    if not precio_obj:
        return Decimal('0')
    precio_dia = Decimal(str(precio_obj.precio_por_dia or 0))
    ajuste = precio_obj.ajuste_porcentaje or 0
    if ajuste != 0:
        precio_dia *= Decimal('1') - Decimal(str(ajuste)) / Decimal('100')
    return precio_dia


def calcular_precio_total_reserva_fechas(fecha_inicio, fecha_fin, precios_map):
    """Misma regla que buscar_propiedades: noches + día de comisión (el más caro)."""
    noches = (fecha_fin - fecha_inicio).days
    if noches <= 0:
        return Decimal('0')
    precio_total = Decimal('0')
    precio_mas_caro = Decimal('0')
    for noche in range(noches):
        dia_salida = fecha_inicio + timedelta(noche)
        dia_llegada = fecha_inicio + timedelta(noche + 1)
        if (
            dia_salida.month == 12
            and dia_salida.day == 31
            and dia_llegada.month == 1
            and dia_llegada.day == 1
        ):
            dia_a_usar = dia_llegada
        else:
            dia_a_usar = dia_salida
        tipo = tipo_precio_para_dia_reserva(dia_a_usar)
        precio_dia = precio_dia_desde_obj(precios_map.get(tipo))
        if precio_dia > precio_mas_caro:
            precio_mas_caro = precio_dia
        precio_total += precio_dia
    return precio_total + precio_mas_caro


def periodo_cubierto_por_disponibilidades(disponibilidades_list, fecha_inicio, fecha_fin):
    """True si las disponibilidades contiguas cubren [fecha_inicio, fecha_fin]."""
    if not disponibilidades_list:
        return False, None, None
    ordenadas = sorted(disponibilidades_list, key=lambda d: d.fecha_inicio)
    cobertura_inicio = ordenadas[0].fecha_inicio
    cobertura_fin = ordenadas[0].fecha_fin
    for disp in ordenadas[1:]:
        if disp.fecha_inicio <= cobertura_fin:
            cobertura_fin = max(cobertura_fin, disp.fecha_fin)
        else:
            break
    cubierto = cobertura_inicio <= fecha_inicio and cobertura_fin >= fecha_fin
    return cubierto, cobertura_inicio, cobertura_fin


def cargar_contexto_bulk_busqueda(propiedad_ids, fecha_inicio, fecha_fin):
    """Precarga disponibilidades, reservas, contratos y recibos para un lote de propiedades."""
    from inmobiliaria.models import ContratoAlquiler, Disponibilidad, Recibo, Reserva

    if not propiedad_ids:
        return {
            'disp_por_prop': {},
            'reservas_por_prop': {},
            'contratos_por_prop': {},
            'reserva_ids_con_recibo': set(),
            'max_fin_anterior_por_prop': {},
            'min_inicio_posterior_por_prop': {},
        }

    disp_por_prop = defaultdict(list)
    for d in Disponibilidad.objects.filter(
        propiedad_id__in=propiedad_ids,
        fecha_inicio__lt=fecha_fin,
        fecha_fin__gt=fecha_inicio,
    ):
        disp_por_prop[d.propiedad_id].append(d)

    reservas_por_prop = defaultdict(list)
    # Solo solapamiento con el rango y reservas que terminan el día de entrada (amarillo).
    # No cargar todo el historial: límites de disponibilidad van en agregados aparte.
    reservas_qs = Reserva.objects.filter(
        propiedad_id__in=propiedad_ids,
        eliminada=False,
    ).filter(
        Q(fecha_inicio__lt=fecha_fin, fecha_fin__gt=fecha_inicio)
        | Q(fecha_fin=fecha_inicio)
    )
    reserva_ids = []
    for r in reservas_qs:
        reservas_por_prop[r.propiedad_id].append(r)
        reserva_ids.append(r.pk)

    max_fin_anterior_por_prop = {
        row['propiedad_id']: row['max_fin']
        for row in Reserva.objects.filter(
            propiedad_id__in=propiedad_ids,
            eliminada=False,
            fecha_fin__lte=fecha_inicio,
        ).values('propiedad_id').annotate(max_fin=Max('fecha_fin'))
    }
    min_inicio_posterior_por_prop = {
        row['propiedad_id']: row['min_inicio']
        for row in Reserva.objects.filter(
            propiedad_id__in=propiedad_ids,
            eliminada=False,
            fecha_inicio__gte=fecha_fin,
        ).values('propiedad_id').annotate(min_inicio=Min('fecha_inicio'))
    }

    reserva_ids_con_recibo = set()
    if reserva_ids:
        reserva_ids_con_recibo = set(
            Recibo.objects.filter(reserva_id__in=reserva_ids).values_list('reserva_id', flat=True)
        )

    contratos_por_prop = defaultdict(list)
    for c in ContratoAlquiler.objects.filter(
        propiedad_id__in=propiedad_ids,
        estado__in=['reservado', 'activo'],
    ):
        contratos_por_prop[c.propiedad_id].append(c)

    return {
        'disp_por_prop': disp_por_prop,
        'reservas_por_prop': reservas_por_prop,
        'contratos_por_prop': contratos_por_prop,
        'reserva_ids_con_recibo': reserva_ids_con_recibo,
        'max_fin_anterior_por_prop': max_fin_anterior_por_prop,
        'min_inicio_posterior_por_prop': min_inicio_posterior_por_prop,
    }


def reservas_solapan_rango(reservas, fecha_inicio, fecha_fin):
    return [
        r
        for r in reservas
        if r.fecha_inicio < fecha_fin and r.fecha_fin > fecha_inicio
    ]


def buscar_reserva_termina_en_inicio_mem(reservas, fecha_inicio, reserva_ids_con_recibo):
    from inmobiliaria.caja_devolucion_deposito import reserva_para_amarillo_termina_en_inicio

    for reserva in reservas:
        if getattr(reserva, 'es_alquiler_sindicato', False):
            continue
        if reserva.fecha_fin != fecha_inicio or reserva.fecha_inicio == fecha_inicio:
            continue
        if reserva.pk in reserva_ids_con_recibo:
            continue
        if reserva_para_amarillo_termina_en_inicio(
            reserva, reserva_ids_con_recibo=reserva_ids_con_recibo
        ):
            return reserva
    return None


def contrato_solapa_rango(contratos, fecha_inicio, fecha_fin):
    for c in contratos:
        if c.fecha_inicio < fecha_fin and c.fecha_fin > fecha_inicio:
            return True
    return False
