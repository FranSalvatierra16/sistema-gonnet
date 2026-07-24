"""Devolución de depósito en garantía desde caja (egreso por operación/reserva)."""
from __future__ import annotations

import json
import re
from datetime import timedelta
from decimal import Decimal

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum

CONCEPTO_DEVOLUCION_DEPOSITO_ID = '140'
CONCEPTOS_SENIA_OPERACION_RESERVA = frozenset({'1', '15', '50', '100', '103', '219'})
CONCEPTO_DEPOSITO_RESERVA_ID = '10'


def concepto_devolucion_deposito_catalogo(sucursal):
    """Concepto 140 (devolución de depósitos) visible para la sucursal."""
    from inmobiliaria.catalogo_conceptos_caja import q_conceptos_caja_visibles
    from inmobiliaria.models.caja import Concepto

    cat = Concepto.objects.filter(
        q_conceptos_caja_visibles(sucursal),
        id=CONCEPTO_DEVOLUCION_DEPOSITO_ID,
    ).first()
    if cat:
        return {'id': str(cat.id), 'nombre': cat.nombre or ''}
    cat = (
        Concepto.objects.filter(q_conceptos_caja_visibles(sucursal))
        .filter(nombre__icontains='devoluc')
        .filter(nombre__icontains='deposit')
        .first()
    )
    if cat:
        return {'id': str(cat.id), 'nombre': cat.nombre or ''}
    return {'id': CONCEPTO_DEVOLUCION_DEPOSITO_ID, 'nombre': 'Devolución de depósitos'}


def es_concepto_devolucion_deposito(concepto_row=None, *, concepto_id: str = '', nombre: str = '') -> bool:
    """True si el concepto de caja es devolución de depósito en garantía (D.D.G.)."""
    if concepto_row is not None:
        concepto_id = str(getattr(concepto_row, 'id', '') or '')
        nombre = str(getattr(concepto_row, 'nombre', '') or '')
    cid = str(concepto_id or '').strip()
    if cid == CONCEPTO_DEVOLUCION_DEPOSITO_ID:
        return True
    texto = f'{concepto_id} {nombre}'.lower()
    return 'devoluc' in texto and (
        'deposit' in texto or 'depósit' in texto or 'garant' in texto or 'ddg' in texto
    )


def _parse_conceptos_movimiento(movimiento) -> list:
    raw = (getattr(movimiento, 'concepto_detalle', None) or '').strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and isinstance(parsed.get('conceptos'), list):
                return parsed['conceptos']
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    conc = (getattr(movimiento, 'concepto', None) or '').strip()
    if '|CONCEPTOS:' in conc:
        trozo = conc.split('|CONCEPTOS:', 1)[1]
        out = []
        for item in [x for x in trozo.split('|') if x.strip()]:
            parts = item.split(':')
            if len(parts) >= 3:
                out.append({'id': parts[0].strip(), 'nombre': parts[1].strip(), 'importe': parts[2].strip()})
        return out
    return []


def _movimiento_vinculado_reserva(movimiento, reserva_id: int) -> bool:
    rid = int(reserva_id)
    conc = (getattr(movimiento, 'concepto', None) or '')
    if re.search(rf'Operaci[oó]n\s*#?\s*{rid}\b', conc, re.IGNORECASE):
        return True
    if re.search(rf'Reserva\s*#?\s*{rid}\b', conc, re.IGNORECASE):
        return True
    if re.search(rf'Devoluci[oó]n dep[oó]sito operaci[oó]n\s*{rid}\b', conc, re.IGNORECASE):
        return True
    raw = (getattr(movimiento, 'concepto_detalle', None) or '')
    if raw and str(rid) in raw and (
        f'"devolucion_deposito_operacion_id": {rid}' in raw
        or f'"devolucion_deposito_operacion_id":{rid}' in raw
        or f'"reserva_id": {rid}' in raw
        or f'"reserva_id":{rid}' in raw
        or f'"operacion_id": {rid}' in raw
        or f'"operacion_id":{rid}' in raw
    ):
        return True
    return False


def movimientos_reserva(reserva, *, tipo=None):
    qs = MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        propiedad=reserva.propiedad,
        fecha_eliminacion__isnull=True,
    )
    if tipo:
        qs = qs.filter(tipo=tipo)
    rid = int(reserva.id)
    return [m for m in qs.order_by('-fecha', '-id') if _movimiento_vinculado_reserva(m, rid)]


def movimiento_tiene_concepto_10(movimiento) -> bool:
    for item in _parse_conceptos_movimiento(movimiento):
        cid = str(item.get('id') or item.get('codigo') or '').strip()
        if cid == '10':
            return True
    conc = (getattr(movimiento, 'concepto', None) or '').lower()
    if 'concepto 10' in conc or (
        'deposito' in conc or 'depósito' in conc
    ) and '|10:' in (getattr(movimiento, 'concepto', None) or ''):
        return True
    return False


def _ingresos_propiedad_en_ventana_reserva(reserva):
    hoy = timezone.now().date()
    fc = reserva.fecha_creacion.date() if getattr(reserva, 'fecha_creacion', None) else hoy
    fi = reserva.fecha_inicio or hoy
    ff = reserva.fecha_fin or hoy
    desde = min(fc, fi) - timedelta(days=45)
    hasta = max(fc, ff) + timedelta(days=14)
    return MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        propiedad=reserva.propiedad,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        fecha_eliminacion__isnull=True,
        fecha__date__gte=desde,
        fecha__date__lte=hasta,
    ).order_by('-fecha', '-id')


def _reserva_id_en_movimiento(movimiento) -> int | None:
    """ID de operación/reserva explícito en el movimiento, si existe."""
    conc = (getattr(movimiento, 'concepto', None) or '')
    for pattern in (
        r'Operaci[oó]n\s*#?\s*(\d+)\b',
        r'Reserva\s*#?\s*(\d+)\b',
        r'Devoluci[oó]n dep[oó]sito operaci[oó]n\s*(\d+)\b',
    ):
        m = re.search(pattern, conc, re.IGNORECASE)
        if m:
            return int(m.group(1))
    raw = (getattr(movimiento, 'concepto_detalle', None) or '')
    if raw:
        for key in (
            'devolucion_deposito_operacion_id',
            'operacion_id',
            'reserva_id',
        ):
            m = re.search(rf'"{key}"\s*:\s*(\d+)', raw)
            if m:
                return int(m.group(1))
    return None


def monto_deposito_cobrado_reserva(reserva) -> Decimal:
    total = Decimal('0')
    vistos: set[int] = set()
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        vistos.add(int(mov.id))
        for item in _parse_conceptos_movimiento(mov):
            cid = str(item.get('id') or item.get('codigo') or '').strip()
            if cid != '10':
                continue
            total += parse_decimal_monto(item.get('importe'))
    if total > Decimal('0'):
        return total
    # Fallback: ingresos con concepto 10 en la propiedad cerca de las fechas de la reserva
    for mov in _ingresos_propiedad_en_ventana_reserva(reserva):
        if int(mov.id) in vistos:
            continue
        sub = Decimal('0')
        for item in _parse_conceptos_movimiento(mov):
            cid = str(item.get('id') or item.get('codigo') or '').strip()
            if cid != '10':
                continue
            sub += parse_decimal_monto(item.get('importe'))
        if sub > Decimal('0'):
            total += sub
    return total


def deposito_estado_reserva(reserva) -> str:
    if not reserva or not Decimal(str(reserva.deposito_garantia or 0)):
        return 'no_aplica'
    if monto_deposito_cobrado_reserva(reserva) > Decimal('0.05'):
        return 'pagado'
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        if movimiento_tiene_concepto_10(mov):
            return 'pagado'
    return 'pendiente'


def _monto_total_movimiento(movimiento) -> Decimal:
    """Total del movimiento: ARS + USD (efectivo dólar). Misma unidad que conceptos si la operación es USD."""
    return (
        Decimal(str(getattr(movimiento, 'monto_efectivo', None) or 0))
        + Decimal(str(getattr(movimiento, 'monto_cheque', None) or 0))
        + Decimal(str(getattr(movimiento, 'monto_tarjeta', None) or 0))
        + Decimal(str(getattr(movimiento, 'monto_deposito', None) or 0))
        + Decimal(str(getattr(movimiento, 'monto_dolares', None) or 0))
    )


def _texto_indica_pago_senia(texto: str) -> bool:
    t = (texto or '').lower()
    if not t:
        return False
    if 'devoluc' in t and ('deposit' in t or 'depósit' in t or 'garant' in t):
        return False
    marcadores = (
        'seña',
        'senia',
        'cuenta de loc',
        'a cuenta de loc',
        'locación y honorarios',
        'locacion y honorarios',
        'alquiler a cobrar',
    )
    return any(m in t for m in marcadores)


def _monto_concepto_en_movimiento(movimiento, concepto_id: str) -> Decimal:
    total = Decimal('0')
    cid_buscar = str(concepto_id or '').strip()
    for item in _parse_conceptos_movimiento(movimiento):
        cid = str(item.get('id') or item.get('codigo') or '').strip()
        if cid == cid_buscar:
            total += parse_decimal_monto(item.get('importe'))
    return total


def monto_senia_en_movimiento(movimiento, *, reserva_id: int | None = None) -> Decimal:
    """Importe del movimiento que cuenta como seña / a cuenta de locación (no depósito)."""
    if getattr(movimiento, 'tipo', None) != TipoMovimientoCajaEnum.INGRESO:
        return Decimal('0')
    if getattr(movimiento, 'fecha_eliminacion', None):
        return Decimal('0')

    conc = (getattr(movimiento, 'concepto', None) or '')
    conc_l = conc.lower()
    if 'devoluc' in conc_l and ('deposit' in conc_l or 'depósit' in conc_l or 'garant' in conc_l):
        return Decimal('0')

    if reserva_id is not None:
        rid = int(reserva_id)
        mov_rid = _reserva_id_en_movimiento(movimiento)
        if mov_rid is not None and mov_rid != rid:
            return Decimal('0')
        if not _movimiento_vinculado_reserva(movimiento, rid):
            return Decimal('0')

    senia = Decimal('0')
    parsed = _parse_conceptos_movimiento(movimiento)
    if parsed:
        for item in parsed:
            cid = str(item.get('id') or item.get('codigo') or '').strip()
            if cid == CONCEPTO_DEPOSITO_RESERVA_ID:
                continue
            if cid in CONCEPTOS_SENIA_OPERACION_RESERVA:
                senia += parse_decimal_monto(item.get('importe'))
        if senia > Decimal('0'):
            return senia

    total = _monto_total_movimiento(movimiento)
    if total <= Decimal('0'):
        return Decimal('0')

    dep10 = _monto_concepto_en_movimiento(movimiento, CONCEPTO_DEPOSITO_RESERVA_ID)
    if dep10 <= Decimal('0') and movimiento_tiene_concepto_10(movimiento):
        dep10 = total

    resto = total - dep10
    if resto <= Decimal('0.01'):
        return Decimal('0')

    if _texto_indica_pago_senia(conc):
        return resto
    if reserva_id is not None and _movimiento_vinculado_reserva(movimiento, reserva_id):
        return resto
    return Decimal('0')


def _total_cobrado_desde_recibos_reserva(reserva) -> Decimal:
    """Suma de importes en recibos emitidos (respaldo si el vínculo al movimiento falla)."""
    from inmobiliaria.models import Recibo

    return sum(
        (Decimal(str(r.monto_este_pago or 0)) for r in Recibo.objects.filter(reserva_id=reserva.id)),
        Decimal('0'),
    ).quantize(Decimal('0.01'))


def _total_movimientos_rows(movimientos_rows) -> Decimal:
    total = Decimal('0')
    for mov in movimientos_rows or []:
        total += (
            Decimal(str(mov.get('monto_efectivo') or 0))
            + Decimal(str(mov.get('monto_cheque') or 0))
            + Decimal(str(mov.get('monto_tarjeta') or 0))
            + Decimal(str(mov.get('monto_deposito') or 0))
            + Decimal(str(mov.get('monto_dolares') or 0))
        )
    return total.quantize(Decimal('0.01'))


def senia_estimada_listado_operacion(
    *,
    senia_guardada,
    movimientos_rows=None,
    total_recibos: Decimal | None = None,
    estado: str = '',
    es_alquiler_sindicato: bool = False,
) -> Decimal:
    """
    Seña para listados (solo lectura): movimientos/recibos vinculados, o BD si está pagada/sindicato.
    Ignora reserva.senia guardada solo en reservas «confirmada» sin cobro real (seña fantasma).
    """
    total_mov = _total_movimientos_rows(movimientos_rows)
    total_rec = Decimal(str(total_recibos or 0))
    if total_mov > Decimal('0.01') or total_rec > Decimal('0.01'):
        return max(total_mov, total_rec).quantize(Decimal('0.01'))
    senia_db = Decimal(str(senia_guardada or 0))
    estado_norm = (estado or '').strip()
    if senia_db > Decimal('0.01') and (
        estado_norm == 'pagada' or es_alquiler_sindicato
    ):
        return senia_db.quantize(Decimal('0.01'))
    return Decimal('0')


def total_senia_pagada_reserva(reserva) -> Decimal:
    rid = int(reserva.id)
    total_mov = Decimal('0')
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        total_mov += monto_senia_en_movimiento(mov, reserva_id=rid)
    total_rec = _total_cobrado_desde_recibos_reserva(reserva)
    return max(total_mov, total_rec).quantize(Decimal('0.01'))


def _estado_reserva_segun_senia(reserva, senia: Decimal) -> str:
    """
    Sin cobro → reservado; seña parcial → operación (`confirmada`);
    alquiler cubierto → `pagada`.
    """
    estado_actual = (getattr(reserva, 'estado', None) or '').strip()
    if estado_actual == 'cancelada':
        return estado_actual

    precio = Decimal(str(getattr(reserva, 'precio_total', None) or 0))
    if senia <= Decimal('0.01'):
        if estado_actual in ('pagada', 'confirmada'):
            return 'confirmada_no_pagada'
        if estado_actual == 'en_espera':
            return 'en_espera'
        return estado_actual or 'confirmada_no_pagada'

    if precio > Decimal('0') and senia >= precio - Decimal('0.01'):
        return 'pagada'
    return 'confirmada'


def etiqueta_estado_reserva(reserva, senia: Decimal | None = None) -> str:
    """Texto visible del estado según cobro real (no el valor crudo de BD)."""
    if senia is None:
        senia = Decimal(str(getattr(reserva, 'senia', None) or 0))
    else:
        senia = Decimal(str(senia or 0))
    estado_actual = (getattr(reserva, 'estado', None) or '').strip()
    if estado_actual == 'cancelada':
        return 'Cancelada'
    if estado_actual == 'en_espera' and senia <= Decimal('0.01'):
        return 'En Espera'

    precio = Decimal(str(getattr(reserva, 'precio_total', None) or 0))
    if senia <= Decimal('0.01'):
        return 'Reservado'
    if precio > Decimal('0') and senia >= precio - Decimal('0.01'):
        return 'Pagada'
    return 'Operación (seña pagada)'


def reserva_tiene_senia_cobrada(reserva) -> bool:
    """True si hay seña u otro cobro de operación registrado en caja."""
    senia_db = Decimal(str(getattr(reserva, 'senia', None) or 0))
    if senia_db > Decimal('0.01'):
        return True
    return total_senia_pagada_reserva(reserva) > Decimal('0.01')


def reserva_tiene_cobro_vinculado_directo(reserva, reserva_ids_con_recibo=None) -> bool:
    """
    Cobro atribuible a esta reserva (campo seña, movimientos vinculados o recibo).
    No usa el fallback por ingresos de la propiedad: ese respaldo puede marcar
    cobro en otra operación y ocultar reservas que sí figuran como pendientes en el listado.
    """
    if (getattr(reserva, 'estado', None) or '').strip() == 'pagada':
        return True
    senia_db = Decimal(str(getattr(reserva, 'senia', None) or 0))
    if senia_db > Decimal('0.01'):
        return True
    rid = int(reserva.pk)
    if reserva_ids_con_recibo is not None:
        if rid in reserva_ids_con_recibo:
            return True
    else:
        from inmobiliaria.models import Recibo

        if Recibo.objects.filter(reserva_id=rid).exists():
            return True
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        if monto_senia_en_movimiento(mov, reserva_id=rid) > Decimal('0.01'):
            return True
    if reserva_ids_con_recibo is None and _total_cobrado_desde_recibos_reserva(reserva) > Decimal('0.01'):
        return True
    return False


def reserva_tuvo_operacion_en_caja(reserva) -> bool:
    """Reserva con cobro en caja (no solo bloqueo de fechas en calendario)."""
    if (getattr(reserva, 'estado', None) or '').strip() == 'pagada':
        return True
    if Decimal(str(getattr(reserva, 'senia', None) or 0)) > Decimal('0.01'):
        return True
    if _total_cobrado_desde_recibos_reserva(reserva) > Decimal('0.01'):
        return True
    return total_senia_pagada_reserva(reserva) > Decimal('0.01')


def queryset_reservas_con_operacion(qs):
    """
    Reservas que deben figurar en listados de operaciones y carátulas.
    Excluye las que siguen en «Reservado» sin seña ni recibo.
    """
    from inmobiliaria.models import Recibo

    tiene_recibo = Exists(Recibo.objects.filter(reserva_id=OuterRef('pk')))
    return qs.filter(
        Q(senia__gt=Decimal('0.01'))
        | tiene_recibo
        | Q(estado='pagada')
    ).distinct()


def queryset_reservas_listado_operaciones(qs):
    """
    Reservas para el listado de operaciones: con cobro real o pagadas / sindicato.
    Excluye seña fantasma en BD (senia>0 sin recibo, sin pagada y sin sindicato).
    """
    from inmobiliaria.models import Recibo

    tiene_recibo = Exists(Recibo.objects.filter(reserva_id=OuterRef('pk')))
    return (
        qs.filter(
            Q(senia__gt=Decimal('0.01'))
            | tiene_recibo
            | Q(estado='pagada')
            | Q(es_alquiler_sindicato=True)
        )
        .exclude(
            Q(senia__gt=Decimal('0.01'))
            & ~tiene_recibo
            & ~Q(estado='pagada')
            & ~Q(es_alquiler_sindicato=True)
        )
        .distinct()
    )


def deposito_pagado_en_movimientos_rows(movimientos_rows) -> bool:
    for movimiento in movimientos_rows or []:
        conc = movimiento.get('concepto') or ''
        if not conc or '|CONCEPTOS:' not in conc:
            continue
        concepto_parts = conc.split('|CONCEPTOS:', 1)
        if len(concepto_parts) <= 1:
            continue
        conceptos_data = concepto_parts[1]
        if '|10:' in conceptos_data or ':10:' in conceptos_data:
            return True
        for concepto_item in [x for x in conceptos_data.split('|') if x.strip()]:
            parts = concepto_item.split(':', 1)
            if parts and parts[0].strip() == '10':
                return True
    return False


def movimientos_ingreso_reservas_por_ids(sucursal_id, reserva_ids, propiedad_ids):
    """Ingresos de caja vinculados a operaciones (solo IDs pedidos)."""
    from collections import defaultdict

    if not reserva_ids or not propiedad_ids:
        return {}
    reserva_ids_set = {int(x) for x in reserva_ids}
    out = defaultdict(list)
    qs = MovimientoCaja.objects.filter(
        sucursal_id=sucursal_id,
        propiedad_id__in=propiedad_ids,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        concepto__icontains='Operación',
    ).values(
        'id',
        'propiedad_id',
        'concepto',
        'fecha',
        'monto_efectivo',
        'monto_cheque',
        'monto_tarjeta',
        'monto_deposito',
        'monto_dolares',
    )
    for row in qs.iterator(chunk_size=500):
        conc = row.get('concepto') or ''
        if not conc:
            continue
        match = re.search(r'Operaci[oó]n\s*#?\s*(\d+)', conc, re.IGNORECASE)
        if not match:
            continue
        rid = int(match.group(1))
        if rid in reserva_ids_set:
            out[rid].append(row)
    for rid in out:
        out[rid].sort(key=lambda r: (r['fecha'] is not None, r['fecha'], r['id']), reverse=True)
    return dict(out)


def movimientos_ingreso_contratos_por_ids(sucursal_id, contrato_ids, propiedad_ids):
    """Ingresos de caja vinculados a contratos invierno (solo IDs pedidos)."""
    from collections import defaultdict

    if not contrato_ids or not propiedad_ids:
        return {}
    contrato_ids_set = {int(x) for x in contrato_ids}
    out = defaultdict(list)
    qs = MovimientoCaja.objects.filter(
        sucursal_id=sucursal_id,
        propiedad_id__in=propiedad_ids,
        tipo=TipoMovimientoCajaEnum.INGRESO,
        concepto__icontains='Contrato #',
    ).values(
        'id',
        'propiedad_id',
        'concepto',
        'fecha',
        'monto_efectivo',
        'monto_cheque',
        'monto_tarjeta',
        'monto_deposito',
    )
    for row in qs.iterator(chunk_size=500):
        conc = row.get('concepto') or ''
        if not conc:
            continue
        match = re.search(r'Contrato\s*#\s*(\d+)', conc, re.IGNORECASE)
        if not match:
            continue
        cid = int(match.group(1))
        if cid in contrato_ids_set:
            out[cid].append(row)
    for cid in out:
        out[cid].sort(key=lambda r: (r['fecha'] is not None, r['fecha'], r['id']), reverse=True)
    return dict(out)


def queryset_reservas_pendientes_cobro(qs):
    """
    Reservas para «Reservas pendientes»: en espera o reservadas sin cobro.
    Excluye sindicato, recibos emitidos y operaciones ya señadas.
    """
    from django.db.models import F

    from inmobiliaria.models import HistorialDisponibilidad, Recibo

    tiene_recibo = Exists(Recibo.objects.filter(reserva_id=OuterRef('pk')))
    en_historial_sindicato = Exists(
        HistorialDisponibilidad.objects.filter(
            reserva_id=OuterRef('pk'),
            estado='alquiler_sindicato',
        )
    )
    return (
        qs.filter(
            estado__in=('en_espera', 'confirmada_no_pagada'),
            es_alquiler_sindicato=False,
        )
        .exclude(
            Q(senia__gt=Decimal('0.01'))
            | tiene_recibo
            | en_historial_sindicato
            | Q(precio_total__gt=0, senia__gte=F('precio_total'))
        )
        .distinct()
    )


def queryset_contratos_con_operacion(qs):
    """Contratos con operación iniciada (no solo estado reservado sin cobro)."""
    return qs.exclude(Q(estado='reservado') & Q(operacion_principal=False))


def reserva_ocupa_sin_ofrecer_en_busqueda(reserva, reserva_ids_con_recibo=None) -> bool:
    """
    Reserva pagada o con seña: no se ofrece en búsqueda (ni disponible ni «reservada sin pagar»).
    """
    if getattr(reserva, 'es_alquiler_sindicato', False):
        return False
    return reserva_tiene_cobro_vinculado_directo(
        reserva, reserva_ids_con_recibo=reserva_ids_con_recibo
    )


def reserva_mostrar_como_reservada_sin_pagar(reserva, reserva_ids_con_recibo=None) -> bool:
    """Misma noción que «Reservas pendientes»: sin cobro vinculado a la reserva."""
    if getattr(reserva, 'es_alquiler_sindicato', False):
        return False
    if reserva_ocupa_sin_ofrecer_en_busqueda(
        reserva, reserva_ids_con_recibo=reserva_ids_con_recibo
    ):
        return False
    return (getattr(reserva, 'estado', None) or '').strip() in (
        'confirmada_no_pagada',
        'en_espera',
    )


def reserva_para_amarillo_termina_en_inicio(reserva, reserva_ids_con_recibo=None) -> bool:
    """
    Amarillo en búsqueda: entra un huésped el mismo día que sale otro, pero solo si lo anterior
    es reserva sin operación (sin seña cobrada, recibo ni pagada). Si ya es operación, no amarillo.
    """
    if getattr(reserva, 'es_alquiler_sindicato', False):
        return False
    if reserva_ocupa_sin_ofrecer_en_busqueda(
        reserva, reserva_ids_con_recibo=reserva_ids_con_recibo
    ):
        return False
    rid = int(reserva.pk)
    if reserva_ids_con_recibo is not None:
        if rid in reserva_ids_con_recibo:
            return False
    else:
        from inmobiliaria.models import Recibo

        if Recibo.objects.filter(reserva_id=rid).exists():
            return False
    return (getattr(reserva, 'estado', None) or '').strip() in (
        'confirmada_no_pagada',
        'en_espera',
        'confirmada',
    )


def buscar_reserva_termina_en_inicio_para_amarillo(propiedad, fecha_inicio):
    """Reserva que cierra en fecha_inicio y debe pintar la fila en amarillo (no operación)."""
    if not propiedad or not fecha_inicio:
        return None
    for reserva in propiedad.reservas.filter(
        eliminada=False,
        fecha_fin=fecha_inicio,
        es_alquiler_sindicato=False,
    ).exclude(fecha_inicio=fecha_inicio):
        if reserva_para_amarillo_termina_en_inicio(reserva):
            return reserva
    return None


def sincronizar_senia_reserva_desde_movimientos(reserva, *, persistir: bool = True) -> Decimal:
    """Recalcula seña, saldo y estado de la reserva desde ingresos de caja vinculados."""
    total_mov = Decimal('0')
    rid = int(reserva.id)
    for mov in movimientos_reserva(reserva, tipo=TipoMovimientoCajaEnum.INGRESO):
        total_mov += monto_senia_en_movimiento(mov, reserva_id=rid)
    total_rec = _total_cobrado_desde_recibos_reserva(reserva)
    total = max(total_mov, total_rec).quantize(Decimal('0.01'))

    precio = Decimal(str(reserva.precio_total or 0))

    cuota = max(precio - total, Decimal('0'))
    estado_actual = (reserva.estado or '').strip()
    nuevo_estado = _estado_reserva_segun_senia(reserva, total)

    # Con recibos emitidos no degradar a «sin pagar» por un fallo al leer movimientos.
    if total_rec > Decimal('0.01'):
        if total < total_rec:
            total = total_rec
            cuota = max(precio - total, Decimal('0'))
            nuevo_estado = _estado_reserva_segun_senia(reserva, total)
        if estado_actual == 'pagada' and precio > Decimal('0') and total >= precio - Decimal('0.01'):
            nuevo_estado = 'pagada'
        elif (
            estado_actual in ('pagada', 'confirmada')
            and total > Decimal('0.01')
            and nuevo_estado in ('confirmada_no_pagada', 'en_espera')
        ):
            nuevo_estado = _estado_reserva_segun_senia(reserva, total)

    update_fields: list[str] = []
    actual = Decimal(str(reserva.senia or 0))
    if abs(actual - total) > Decimal('0.01'):
        reserva.senia = total
        update_fields.append('senia')
    actual_cuota = Decimal(str(reserva.cuota_pendiente or 0))
    if abs(actual_cuota - cuota) > Decimal('0.01'):
        reserva.cuota_pendiente = cuota
        update_fields.append('cuota_pendiente')
    if nuevo_estado != estado_actual:
        reserva.estado = nuevo_estado
        update_fields.append('estado')

    reserva.senia = total
    reserva.cuota_pendiente = cuota
    reserva.estado = nuevo_estado

    if persistir and update_fields:
        reserva.save(update_fields=update_fields)
        if any(campo in update_fields for campo in ('senia', 'estado')):
            reserva.actualizar_historial_disponibilidad()
    return total


def _egreso_es_devolucion_deposito_reserva(movimiento, reserva, nombre_concepto_140: str = '') -> bool:
    rid = int(reserva.id)
    conc = (getattr(movimiento, 'concepto', None) or '')
    conc_l = conc.lower()
    raw = (getattr(movimiento, 'concepto_detalle', None) or '')
    if f'"devolucion_deposito_operacion_id": {rid}' in raw or f'"devolucion_deposito_operacion_id":{rid}' in raw:
        return True
    if _movimiento_vinculado_reserva(movimiento, rid) and es_concepto_devolucion_deposito(nombre=conc):
        return True
    nom140 = (nombre_concepto_140 or '').strip().lower()
    if nom140 and nom140 in conc_l:
        if re.search(rf'Operaci[oó]n\s*#?\s*{rid}\b', conc, re.IGNORECASE):
            return True
        if re.search(rf'Devoluci[oó]n dep[oó]sito operaci[oó]n\s*{rid}\b', conc, re.IGNORECASE):
            return True
    if re.search(rf'Devoluci[oó]n dep[oó]sito operaci[oó]n\s*{rid}\b', conc, re.IGNORECASE):
        return True
    if re.search(rf'Operaci[oó]n\s*#?\s*{rid}\b', conc, re.IGNORECASE) and 'devoluc' in conc_l:
        return True
    # No usar solo monto≈depósito: en la misma propiedad hay otras ops con el mismo importe
    # y marcaba «ya devuelto» sin egreso de esta operación.
    return False


def ya_devolvio_deposito_reserva(reserva) -> bool:
    rid = int(reserva.id)
    nombre_140 = concepto_devolucion_deposito_catalogo(reserva.sucursal).get('nombre') or ''
    qs = MovimientoCaja.objects.filter(
        sucursal=reserva.sucursal,
        tipo=TipoMovimientoCajaEnum.EGRESO,
        fecha_eliminacion__isnull=True,
    )
    patrones = (
        f'Devolución depósito operación {rid}',
        f'Devolucion deposito operacion {rid}',
        f'"devolucion_deposito_operacion_id": {rid}',
        f'"devolucion_deposito_operacion_id":{rid}',
    )
    q = Q()
    for p in patrones:
        q |= Q(concepto__icontains=p) | Q(concepto_detalle__icontains=p)
    if qs.filter(q).exists():
        return True
    candidatos = qs.filter(propiedad=reserva.propiedad).order_by('-fecha', '-id')
    for mov in candidatos:
        if _egreso_es_devolucion_deposito_reserva(mov, reserva, nombre_140):
            return True
    return False


def monto_devolucion_sugerido_reserva(reserva) -> Decimal:
    cobrado = monto_deposito_cobrado_reserva(reserva)
    if cobrado > Decimal('0'):
        return cobrado
    return Decimal(str(reserva.deposito_garantia or 0))


def datos_operacion_reserva_caja(reserva) -> dict:
    deposito_estado = deposito_estado_reserva(reserva)
    monto_sugerido = monto_devolucion_sugerido_reserva(reserva)
    ya_devuelto = ya_devolvio_deposito_reserva(reserva)
    cliente = getattr(reserva, 'cliente', None)
    cliente_txt = ''
    if cliente:
        ap = (getattr(cliente, 'apellido', None) or '').strip()
        nom = (getattr(cliente, 'nombre', None) or '').strip()
        cliente_txt = f'{ap}, {nom}'.strip(', ') if ap or nom else str(cliente)

    prop = reserva.propiedad
    mensajes = []
    if deposito_estado != 'pagado':
        mensajes.append('No se detectó el cobro del depósito (concepto 10) en caja para esta operación.')
    if ya_devuelto:
        mensajes.append('Ya existe un egreso de devolución de depósito para esta operación.')
    if monto_sugerido <= 0:
        mensajes.append('La operación no tiene monto de depósito a devolver.')

    vendedor = getattr(reserva, 'vendedor', None)
    vendedor_data = None
    if vendedor:
        vendedor_data = {
            'id': int(vendedor.id),
            'nombre': (getattr(vendedor, 'nombre', None) or '').strip(),
            'apellido': (getattr(vendedor, 'apellido', None) or '').strip(),
        }

    return {
        'tipo': 'reserva',
        'id': int(reserva.id),
        'estado': reserva.estado,
        'fecha_desde': reserva.fecha_inicio.isoformat() if reserva.fecha_inicio else '',
        'fecha_hasta': reserva.fecha_fin.isoformat() if reserva.fecha_fin else '',
        'cliente': cliente_txt,
        'deposito_garantia': float(reserva.deposito_garantia or 0),
        'deposito_cobrado': float(monto_deposito_cobrado_reserva(reserva)),
        'deposito_estado': deposito_estado,
        'deposito_ya_devuelto': ya_devuelto,
        'monto_devolucion_sugerido': float(monto_sugerido),
        'puede_devolver': (
            deposito_estado == 'pagado'
            and not ya_devuelto
            and monto_sugerido > 0
        ),
        'mensaje': ' '.join(mensajes),
        'vendedor': vendedor_data,
        'propiedad': {
            'id': prop.id,
            'direccion': prop.direccion or '',
            'ubicacion': getattr(prop, 'ubicacion', None) or '',
            'piso': (prop.piso or '').strip(),
            'departamento': (prop.departamento or '').strip(),
        },
    }


def validar_devolucion_deposito_caja(entidad, monto_total: Decimal, *, tipo: str = 'reserva') -> str | None:
    """None si OK; mensaje de error si no se puede registrar."""
    if not entidad:
        return 'Operación no encontrada.'
    tipo = (tipo or 'reserva').strip().lower()
    eid = int(entidad.id)
    if tipo == 'contrato':
        from inmobiliaria.caja_buscar_operacion import (
            _monto_deposito_cobrado_contrato,
            _ya_devolvio_deposito_contrato,
        )

        if _ya_devolvio_deposito_contrato(entidad):
            return f'Ya se registró la devolución del depósito del contrato #{eid}.'
        cobrado = _monto_deposito_cobrado_contrato(entidad)
        if cobrado <= Decimal('0.05'):
            return (
                f'No se puede devolver el depósito del contrato #{eid}: '
                'no figura cobrado en caja (concepto 10).'
            )
        sugerido = cobrado if cobrado > 0 else Decimal(str(entidad.deposito_garantia or 0))
    else:
        if ya_devolvio_deposito_reserva(entidad):
            return f'Ya se registró la devolución del depósito de la operación #{eid}.'
        if deposito_estado_reserva(entidad) != 'pagado':
            return (
                f'No se puede devolver el depósito de la operación #{eid}: '
                'no figura cobrado en caja (concepto 10).'
            )
        sugerido = monto_devolucion_sugerido_reserva(entidad)
    if sugerido <= Decimal('0'):
        return 'La operación no tiene depósito a devolver.'
    if monto_total <= Decimal('0'):
        return 'El importe del egreso debe ser mayor a cero.'
    return None


def concepto_guardado_devolucion_deposito(entidad, detalles: str = '', *, tipo: str = 'reserva') -> str:
    tipo = (tipo or 'reserva').strip().lower()
    direccion = (getattr(entidad.propiedad, 'direccion', None) or '').strip()
    if tipo == 'contrato':
        base = f'Devolución depósito contrato {entidad.id} - {direccion}'
    else:
        base = f'Devolución depósito operación {entidad.id} - {direccion}'
    extra = (detalles or '').strip()
    txt = f'{base} — {extra}' if extra else base
    return txt[:200]


def payload_concepto_detalle_devolucion(ref_id: int, *, tipo: str = 'reserva') -> str:
    tipo = (tipo or 'reserva').strip().lower()
    data = {'id': CONCEPTO_DEVOLUCION_DEPOSITO_ID}
    if tipo == 'contrato':
        data['devolucion_deposito_contrato_id'] = int(ref_id)
    else:
        data['devolucion_deposito_operacion_id'] = int(ref_id)
    return json.dumps(data, ensure_ascii=False)
