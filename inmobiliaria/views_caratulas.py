"""
Consulta de carátulas: listado y detalle de operaciones (reservas por día, invierno, 24 meses).
"""
import re
from datetime import datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Prefetch, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, render

from inmobiliaria.models import (
    ComisionVendedor,
    ContratoAlquiler,
    CuotaMensual,
    MovimientoCaja,
    Recibo,
    Reserva,
)
from inmobiliaria.models.caja import TipoMovimientoCajaEnum


def _puede_ver_caratulas(user):
    return bool(getattr(user, 'is_superuser', False) or getattr(user, 'nivel', None) == 4)


def _caratula_nombre_cliente(cliente):
    if not cliente:
        return '—'
    ap = (getattr(cliente, 'apellido', None) or '').strip()
    nom = (getattr(cliente, 'nombre', None) or '').strip()
    s = f'{ap}, {nom}'.strip(', ').strip()
    return s if s else '—'


def _tipo_reserva(propiedad):
    if not propiedad:
        return 'Por día'
    if getattr(propiedad, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'Estudiante'
    return 'Por día'


def _formato_miles_ar(val):
    try:
        if val is None:
            return '0'
        n = int(Decimal(str(val)))
        return f'{n:,}'.replace(',', '.')
    except (ValueError, TypeError, ArithmeticError):
        return '0'


def _formato_ficha_legacy(pk):
    if pk is None or pk == '':
        return '—'
    s = str(pk).strip().replace('.', '').replace(',', '')
    if s.isdigit():
        return _formato_miles_ar(int(s))
    return str(pk)


def _formato_importe_us(val):
    """Miles con coma y dos decimales (ej. 320,000.00 como en sistema viejo)."""
    try:
        d = Decimal(str(val or 0)).quantize(Decimal('0.01'))
    except Exception:
        return '0.00'
    neg = d < 0
    d = abs(d)
    whole, frac = f'{d:.2f}'.split('.')
    whole_fmt = f'{int(whole):,}'
    out = f'{whole_fmt}.{frac}'
    return ('-' if neg else '') + out


def _caratula_rotulo_prop_cli(prop, persona_cli):
    letra = '—'
    if prop and getattr(prop, 'propietario', None):
        ap = (prop.propietario.apellido or '').strip()
        if ap:
            letra = ap[0].upper()
    ap_cli = '—'
    if persona_cli:
        x = (persona_cli.apellido or '').strip().upper()
        if x:
            ap_cli = x
    if letra == '—' and ap_cli == '—':
        return '—'
    return f'{letra} - {ap_cli}'


def _tipo_movimiento_codigo_reserva(prop):
    if prop and getattr(prop, 'tipo_cliente', None) == 'ESTUDIANTE':
        return 'invierno'
    return 'alquiler'


def _tipo_movimiento_codigo_contrato(contrato):
    dm = contrato.duracion_meses or 0
    if dm == 9:
        return 'invierno'
    if dm == 24:
        return 'meses_24'
    if dm == 6:
        return 'meses_6'
    return 'otros'


def _dni_formato_legado(dni):
    if not dni:
        return '0'
    digits = ''.join(c for c in str(dni) if c.isdigit())
    if len(digits) >= 7:
        return _formato_miles_ar(int(digits))
    return str(dni).strip() or '0'


def _domicilio_una_linea(persona):
    if not persona:
        return '—'
    parts = [
        (getattr(persona, 'domicilio', None) or '').strip(),
        (getattr(persona, 'localidad', None) or '').strip(),
        (getattr(persona, 'provincia', None) or '').strip(),
    ]
    s = ', '.join(p for p in parts if p)
    return s if s else '—'


def _propietario_legado(propi):
    if not propi:
        return {'id_fmt': '0', 'rotulo': '—', 'ubic': '—'}
    id_fmt = _formato_miles_ar(propi.id)
    rotulo = ((propi.apellido or '').strip()[:1] or '—').upper()
    cp = (getattr(propi, 'codigo_postal', None) or '').strip()
    loc = (propi.localidad or '').strip().upper()
    ubic = f'{cp} {loc}'.strip() or loc or '—'
    return {'id_fmt': id_fmt, 'rotulo': rotulo, 'ubic': ubic}


def _turista_legado(cli):
    if not cli:
        return {'dni': '0', 'nombre': '—', 'dom': '—'}
    ap = (cli.apellido or '').strip().upper()
    nom = (cli.nombre or '').strip().upper()
    nombre_fmt = f'{ap} {nom}'.strip() or '—'
    return {
        'dni': _dni_formato_legado(cli.dni),
        'nombre': nombre_fmt,
        'dom': _domicilio_una_linea(cli).upper(),
    }


def _origen_operacion_sucursal(sucursal):
    if not sucursal:
        return '1 OFICINA'
    sid = getattr(sucursal, 'id', '') or '1'
    nom = (getattr(sucursal, 'nombre', None) or 'OFICINA').strip().upper()
    return f'{sid} {nom}'[:48]


def _build_legacy_reserva(reserva, recibos, comisiones, saldo_reserva, tipo_operacion_str):
    prop = reserva.propiedad
    cli = reserva.cliente
    propi = getattr(prop, 'propietario', None) if prop else None
    vend = reserva.vendedor

    recibo_loc = recibos[0].numero_recibo if recibos else '0000-00000000'
    recibo_locat = recibos[1].numero_recibo if len(recibos) > 1 else '0000-00000000'

    comision_total = sum(Decimal(str(c.monto_comision or 0)) for c in comisiones)

    piso_dto = '—'
    if prop:
        pi = (prop.piso or '').strip()
        dep = (prop.departamento or '').strip()
        piso_dto = f'{pi}{dep}' if pi and dep else (pi or dep or '—')

    llave_cod = '0'
    if prop:
        raw = (getattr(prop, 'llave', None) or '').strip()
        llave_cod = raw if raw else '0'

    productor = '—'
    if vend:
        productor = f'{vend.id} {(vend.apellido or vend.nombre or "")}'.strip().upper()[:48]

    terceros = _formato_miles_ar(vend.id) if vend else '0'

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(reserva.id),
        'fecha_registro': reserva.fecha_creacion,
        'tipo_mov': _tipo_movimiento_codigo_reserva(prop),
        'ficha_prop': _formato_ficha_legacy(prop.id) if prop else '—',
        'dir_prop': (prop.direccion or '—').upper() if prop else '—',
        'piso_depto': piso_dto,
        'codigo_llave': llave_cod,
        'propietario': _propietario_legado(propi),
        'turista': _turista_legado(cli),
        'garante_id': '0',
        'caratula_rotulo': _caratula_rotulo_prop_cli(prop, cli),
        'importe_locacion': _formato_importe_us(reserva.precio_total),
        'senia': _formato_importe_us(reserva.senia),
        'refuerzo': '0.00',
        'fecha_refuerzo': '',
        'deposito': _formato_importe_us(reserva.deposito_garantia),
        'saldo': _formato_importe_us(saldo_reserva),
        'comision_locador': _formato_importe_us(0),
        'comision_locatario': _formato_importe_us(comision_total),
        'recibo_locador': recibo_loc,
        'recibo_locatario': recibo_locat,
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(reserva.sucursal),
        'estado_txt': reserva.get_estado_display(),
        'locacion_mensual': _formato_importe_us(0),
        'carpeta': '0',
        'tipo_operacion_str': tipo_operacion_str,
    }


def _build_legacy_contrato(contrato, cuotas, tipo_label):
    prop = contrato.propiedad
    inq = contrato.inquilino
    propi = getattr(prop, 'propietario', None) if prop else None
    vend = contrato.vendedor

    garantes = list(contrato.garantes.all()[:1])
    if garantes:
        garante_id = _dni_formato_legado(garantes[0].dni)
    elif contrato.garante_dni:
        garante_id = _dni_formato_legado(contrato.garante_dni)
    else:
        garante_id = '0'

    total_contrato = (contrato.precio_mensual or Decimal(0)) * Decimal(contrato.duracion_meses or 0)
    saldo_cuotas = sum(
        Decimal(str(c.monto_total or 0)) for c in cuotas if getattr(c, 'estado', '') == 'pendiente'
    )

    piso_dto = '—'
    if prop:
        pi = (prop.piso or '').strip()
        dep = (prop.departamento or '').strip()
        piso_dto = f'{pi}{dep}' if pi and dep else (pi or dep or '—')

    llave_cod = '0'
    if prop:
        raw = (getattr(prop, 'llave', None) or '').strip()
        llave_cod = raw if raw else '0'

    productor = '—'
    if vend:
        productor = f'{vend.id} {(vend.apellido or vend.nombre or "")}'.strip().upper()[:48]
    terceros = _formato_miles_ar(vend.id) if vend else '0'

    return {
        'numero_original': '0',
        'numero_operacion': _formato_miles_ar(contrato.id),
        # Fecha de cabecera como en legado (día de operación), no alta en sistema
        'fecha_registro': contrato.fecha_operacion,
        'tipo_mov': _tipo_movimiento_codigo_contrato(contrato),
        'ficha_prop': _formato_ficha_legacy(prop.id) if prop else '—',
        'dir_prop': (prop.direccion or '—').upper() if prop else '—',
        'piso_depto': piso_dto,
        'codigo_llave': llave_cod,
        'propietario': _propietario_legado(propi),
        'turista': _turista_legado(inq),
        'garante_id': garante_id,
        'caratula_rotulo': _caratula_rotulo_prop_cli(prop, inq),
        'importe_locacion': _formato_importe_us(total_contrato),
        'senia': _formato_importe_us(0),
        'refuerzo': '0.00',
        'fecha_refuerzo': '',
        'deposito': _formato_importe_us(contrato.deposito_garantia),
        'saldo': _formato_importe_us(saldo_cuotas),
        'comision_locador': _formato_importe_us(0),
        'comision_locatario': _formato_importe_us(0),
        'recibo_locador': '0000-00000000',
        'recibo_locatario': '0000-00000000',
        'productor': productor,
        'terceros': terceros,
        'origen_operacion': _origen_operacion_sucursal(contrato.sucursal),
        'estado_txt': contrato.get_estado_display(),
        'locacion_mensual': _formato_importe_us(contrato.precio_mensual),
        'carpeta': '0',
        'tipo_operacion_str': tipo_label,
    }


@login_required
def lista_caratulas(request):
    """Tabla tipo consultorio: tipo, número, fecha, carátula, dirección, piso/depto, ficha."""
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    sucursal = getattr(request.user, 'sucursal', None)
    q = request.GET.get('q', '').strip()
    fecha_desde = request.GET.get('fecha_desde', '').strip()
    fecha_hasta = request.GET.get('fecha_hasta', '').strip()
    tipo_filtro = request.GET.get('tipo', '').strip()

    if not sucursal:
        paginator_empty = Paginator([], 40)
        return render(
            request,
            'inmobiliaria/caratulas/lista.html',
            {
                'error': 'Tu usuario no tiene sucursal asignada.',
                'filas': paginator_empty.page(1),
                'q': q,
                'fecha_desde': request.GET.get('fecha_desde', '').strip(),
                'fecha_hasta': request.GET.get('fecha_hasta', '').strip(),
                'tipo_filtro': tipo_filtro,
            },
        )

    reservas = (
        Reserva.objects.filter(sucursal=sucursal, eliminada=False)
        .select_related('cliente', 'propiedad', 'propiedad__propietario', 'vendedor')
        .order_by('-fecha_creacion', '-id')
    )

    if tipo_filtro == 'invierno':
        reservas = reservas.none()
    elif tipo_filtro == '24meses':
        reservas = reservas.none()
    elif tipo_filtro == 'estudiante':
        reservas = reservas.filter(propiedad__tipo_cliente='ESTUDIANTE')
    elif tipo_filtro == 'dia':
        reservas = reservas.exclude(propiedad__tipo_cliente='ESTUDIANTE')

    if q:
        reservas = reservas.filter(
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(cliente__nombre__icontains=q)
            | Q(cliente__apellido__icontains=q)
        )

    if fecha_desde:
        try:
            d = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_creacion__date__gte=d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            reservas = reservas.filter(fecha_creacion__date__lte=d)
        except ValueError:
            pass

    contratos = ContratoAlquiler.objects.filter(sucursal=sucursal).select_related(
        'propiedad', 'inquilino', 'vendedor'
    )
    if tipo_filtro == 'invierno':
        contratos = contratos.filter(duracion_meses=9)
    elif tipo_filtro == '24meses':
        contratos = contratos.filter(duracion_meses=24)
    elif tipo_filtro in ('dia', 'estudiante'):
        contratos = contratos.none()

    contratos = contratos.order_by('-fecha_creacion', '-id')

    if q:
        contratos = contratos.filter(
            Q(propiedad__direccion__icontains=q)
            | Q(propiedad__id__icontains=q)
            | Q(inquilino__nombre__icontains=q)
            | Q(inquilino__apellido__icontains=q)
        )
    if fecha_desde:
        try:
            d = datetime.strptime(fecha_desde, '%Y-%m-%d').date()
            contratos = contratos.filter(fecha_operacion__gte=d)
        except ValueError:
            pass
    if fecha_hasta:
        try:
            d = datetime.strptime(fecha_hasta, '%Y-%m-%d').date()
            contratos = contratos.filter(fecha_operacion__lte=d)
        except ValueError:
            pass

    filas = []

    for r in reservas:
        tipo = _tipo_reserva(r.propiedad)
        p = r.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        filas.append(
            {
                'kind': 'reserva',
                'pk': r.id,
                'tipo': tipo,
                'numero': r.id,
                'fecha': r.fecha_creacion.date() if r.fecha_creacion else r.fecha_inicio,
                'caratula': _caratula_nombre_cliente(r.cliente),
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': r.get_estado_display() if hasattr(r, 'get_estado_display') else r.estado,
                'sort': r.fecha_creacion or r.fecha_inicio,
            }
        )

    for c in contratos:
        if c.duracion_meses == 9:
            tipo_c = 'Invierno'
        elif c.duracion_meses == 24:
            tipo_c = '24 meses'
        else:
            tipo_c = f'Contrato ({c.duracion_meses} meses)'
        p = c.propiedad
        piso_dto = ''
        if p:
            pi = (p.piso or '').strip() or '—'
            dep = (p.departamento or '').strip() or '—'
            piso_dto = f'{pi} / {dep}'
        filas.append(
            {
                'kind': 'contrato',
                'pk': c.id,
                'tipo': tipo_c,
                'numero': c.id,
                'fecha': c.fecha_operacion,
                'caratula': _caratula_nombre_cliente(c.inquilino),
                'direccion': p.direccion if p else '—',
                'piso_dto': piso_dto,
                'ficha': p.id if p else '—',
                'estado': c.get_estado_display() if hasattr(c, 'get_estado_display') else c.estado,
                'sort': c.fecha_creacion,
            }
        )

    filas.sort(key=lambda x: x['sort'] or x['fecha'], reverse=True)

    paginator = Paginator(filas, 40)
    page = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages or 1)

    return render(
        request,
        'inmobiliaria/caratulas/lista.html',
        {
            'filas': page_obj,
            'q': q,
            'fecha_desde': fecha_desde,
            'fecha_hasta': fecha_hasta,
            'tipo_filtro': tipo_filtro,
        },
    )


@login_required
def caratula_reserva(request, reserva_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    reserva = get_object_or_404(
        Reserva.objects.select_related(
            'cliente', 'propiedad', 'propiedad__propietario', 'vendedor', 'sucursal'
        )
        .prefetch_related(
            Prefetch('recibos', queryset=Recibo.objects.order_by('-fecha_emision')),
            Prefetch(
                'comisiones_vendedor',
                queryset=ComisionVendedor.objects.select_related('vendedor').exclude(estado='cancelada'),
            ),
        ),
        pk=reserva_id,
    )
    if reserva.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    movimientos = []
    if reserva.propiedad_id:
        movs_qs = (
            MovimientoCaja.objects.filter(
                propiedad_id=reserva.propiedad_id,
                sucursal_id=reserva.sucursal_id,
            )
            .order_by('-fecha')
        )
        for mov in movs_qs[:200]:
            if mov.concepto and re.search(rf'Operaci[oó]n\s+{reserva.id}\b', mov.concepto, re.IGNORECASE):
                movimientos.append(mov)

    recibos = list(reserva.recibos.all())
    comisiones = list(reserva.comisiones_vendedor.all())

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    saldo_reserva = (reserva.precio_total or Decimal('0')) - (reserva.senia or Decimal('0'))
    tipo_op = _tipo_reserva(reserva.propiedad)
    ctx = {
        'reserva': reserva,
        'propiedad': reserva.propiedad,
        'tipo_operacion': tipo_op,
        'movimientos': movimientos,
        'recibos': recibos,
        'comisiones': comisiones,
        'total_movimientos': total_mov,
        'saldo_reserva': saldo_reserva,
        'caratula_legacy': _build_legacy_reserva(reserva, recibos, comisiones, saldo_reserva, tipo_op),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_reserva.html', ctx)


@login_required
def caratula_contrato(request, contrato_id):
    if not _puede_ver_caratulas(request.user):
        return HttpResponseForbidden()
    contrato = get_object_or_404(
        ContratoAlquiler.objects.select_related(
            'propiedad', 'propiedad__propietario', 'inquilino', 'vendedor', 'sucursal'
        ).prefetch_related(
            Prefetch('cuotas', queryset=CuotaMensual.objects.order_by('fecha_vencimiento')),
            'garantes',
        ),
        pk=contrato_id,
    )
    if contrato.sucursal_id != getattr(request.user, 'sucursal_id', None) and not getattr(
        request.user, 'is_superuser', False
    ):
        return HttpResponseForbidden()

    movimientos = []
    if contrato.propiedad_id:
        movs_qs = MovimientoCaja.objects.filter(
            propiedad_id=contrato.propiedad_id,
            sucursal_id=contrato.sucursal_id,
            tipo=TipoMovimientoCajaEnum.INGRESO,
        ).order_by('-fecha')
        for mov in movs_qs[:300]:
            if mov.concepto and re.search(rf'Contrato\s*#\s*{contrato.id}\b', mov.concepto, re.IGNORECASE):
                movimientos.append(mov)

    total_mov = sum(
        Decimal(str(m.monto_efectivo or 0))
        + Decimal(str(m.monto_cheque or 0))
        + Decimal(str(m.monto_tarjeta or 0))
        + Decimal(str(m.monto_deposito or 0))
        for m in movimientos
    )

    cuotas = list(contrato.cuotas.all()) if hasattr(contrato, 'cuotas') else []

    if contrato.duracion_meses == 9:
        tipo_label = 'Invierno (9 meses)'
    elif contrato.duracion_meses == 24:
        tipo_label = '24 meses'
    else:
        tipo_label = f'Contrato {contrato.duracion_meses} meses'

    ctx = {
        'contrato': contrato,
        'propiedad': contrato.propiedad,
        'tipo_label': tipo_label,
        'movimientos': movimientos,
        'total_movimientos': total_mov,
        'cuotas': cuotas,
        'caratula_legacy': _build_legacy_contrato(contrato, cuotas, tipo_label),
    }
    return render(request, 'inmobiliaria/caratulas/detalle_contrato.html', ctx)
