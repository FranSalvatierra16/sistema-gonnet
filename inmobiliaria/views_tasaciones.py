"""Tasaciones: monto en ARS o USD, comisión del productor acreditada el día de la tasación."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inmobiliaria.models import ComisionVendedor, Tasacion, Vendedor
from inmobiliaria.models.comision import ROL_COMISION_TASACION
from inmobiliaria.views_ventas import (
    _fecha_operacion_aware,
    _fmt_decimal_form,
    _parse_decimal,
    _puede_gestionar_ventas,
)

CAMPOS_FORM = (
    'propiedad_nombre',
    'fecha',
    'vendedor_id',
    'moneda',
    'monto',
    'cotizacion_dolar',
    'tipo_comision',
    'porcentaje_comision',
    'comision_monto',
    'cliente_nombre',
    'observaciones',
)


def _form_vacio(request):
    return {
        'propiedad_nombre': '',
        'fecha': timezone.localdate().isoformat(),
        'vendedor_id': str(request.user.pk) if isinstance(request.user, Vendedor) else '',
        'moneda': Tasacion.MONEDA_ARS,
        'monto': '',
        'cotizacion_dolar': '',
        'tipo_comision': Tasacion.TIPO_COMISION_PORCENTAJE,
        'porcentaje_comision': '',
        'comision_monto': '',
        'cliente_nombre': '',
        'observaciones': '',
    }


def _form_desde_tasacion(t):
    return {
        'propiedad_nombre': t.propiedad_nombre,
        'fecha': t.fecha.isoformat() if t.fecha else '',
        'vendedor_id': str(t.vendedor_id),
        'moneda': t.moneda,
        'monto': _fmt_decimal_form(t.monto),
        'cotizacion_dolar': _fmt_decimal_form(t.cotizacion_dolar) if t.cotizacion_dolar else '',
        'tipo_comision': t.tipo_comision,
        'porcentaje_comision': _fmt_decimal_form(t.porcentaje_comision) if t.porcentaje_comision is not None else '',
        'comision_monto': _fmt_decimal_form(t.comision_monto) if t.comision_monto is not None else '',
        'cliente_nombre': t.cliente_nombre,
        'observaciones': t.observaciones,
    }


def _leer_post(request):
    return {k: (request.POST.get(k) or '').strip() for k in CAMPOS_FORM}


def _validar_y_aplicar(form, t, vendedores):
    """Valida el formulario y vuelca los datos en la tasación (sin guardar). Devuelve errores."""
    errores = []
    t.propiedad_nombre = form['propiedad_nombre'][:255]
    if not t.propiedad_nombre:
        errores.append('Indicá la propiedad.')

    try:
        t.fecha = datetime.strptime(form['fecha'][:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        errores.append('Fecha inválida.')

    vend = vendedores.filter(pk=int(form['vendedor_id'])).first() if form['vendedor_id'].isdigit() else None
    if vend is None:
        errores.append('Elegí el productor que hizo la tasación.')
    else:
        t.vendedor = vend

    t.moneda = form['moneda'] if form['moneda'] in (Tasacion.MONEDA_ARS, Tasacion.MONEDA_USD) else Tasacion.MONEDA_ARS
    t.monto = _parse_decimal(form['monto']).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if t.monto <= 0:
        errores.append('El monto de la tasación tiene que ser mayor a 0.')

    if t.moneda == Tasacion.MONEDA_USD:
        t.cotizacion_dolar = _parse_decimal(form['cotizacion_dolar']).quantize(Decimal('0.0001'))
        if t.cotizacion_dolar <= 0:
            errores.append('Indicá el cambio del día (pesos por dólar).')
    else:
        t.cotizacion_dolar = None

    t.tipo_comision = (
        Tasacion.TIPO_COMISION_MONTO
        if form['tipo_comision'] == Tasacion.TIPO_COMISION_MONTO
        else Tasacion.TIPO_COMISION_PORCENTAJE
    )
    if t.tipo_comision == Tasacion.TIPO_COMISION_PORCENTAJE:
        t.porcentaje_comision = _parse_decimal(form['porcentaje_comision']).quantize(Decimal('0.01'))
        t.comision_monto = None
        if t.porcentaje_comision < 0 or t.porcentaje_comision > 100:
            errores.append('El porcentaje de comisión tiene que estar entre 0 y 100.')
    else:
        t.comision_monto = _parse_decimal(form['comision_monto']).quantize(Decimal('0.01'))
        t.porcentaje_comision = None
        if t.comision_monto < 0:
            errores.append('La comisión no puede ser negativa.')

    t.cliente_nombre = form['cliente_nombre'][:255]
    t.observaciones = form['observaciones']
    if not errores:
        t.recalcular()
    return errores


def _comisiones_de_tasacion(t):
    q = Q(rol_comision=ROL_COMISION_TASACION, observaciones__startswith=f'Tasación #{t.pk}.')
    if t.comision_id:
        q |= Q(pk=t.comision_id)
    return ComisionVendedor.objects.filter(q)


def _regenerar_comision(t):
    """Borra la comisión no pagada de la tasación y la vuelve a crear con la fecha de la tasación."""
    qs = _comisiones_de_tasacion(t)
    if qs.filter(estado='pagada').exists():
        raise ValueError('La comisión de esta tasación ya está pagada; no se puede regenerar.')
    t.comision = None
    t.save(update_fields=['comision'])
    qs.delete()

    monto = Decimal(str(t.comision_ars or 0))
    if monto <= 0:
        return None
    if t.tipo_comision == Tasacion.TIPO_COMISION_PORCENTAJE:
        pct = Decimal(str(t.porcentaje_comision or 0))
    elif t.monto_ars > 0:
        pct = min(monto / t.monto_ars * Decimal('100'), Decimal('999.99'))
    else:
        pct = Decimal('0')
    moneda_txt = f'U$S {t.monto} @ {t.cotizacion_dolar}' if t.es_usd else f'${t.monto}'
    comision = ComisionVendedor.objects.create(
        vendedor=t.vendedor,
        monto_total_operacion=t.monto_ars,
        porcentaje_comision=pct.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        monto_comision=monto,
        concepto_operacion=f'Tasación — {t.propiedad_nombre}'[:200],
        rol_comision=ROL_COMISION_TASACION,
        fecha_operacion=_fecha_operacion_aware(t.fecha),
        estado='confirmada',
        observaciones=(
            f'Tasación #{t.pk}. Monto {moneda_txt} = ${t.monto_ars} ARS; '
            f'comisión ${monto} ARS.'
        ),
    )
    t.comision = comision
    t.save(update_fields=['comision'])
    return comision


def _vendedores_form(sucursal, incluir_id=None):
    q = Q(sucursal=sucursal, is_active=True)
    if incluir_id:
        q |= Q(pk=incluir_id)
    return Vendedor.objects.filter(q).order_by('apellido', 'nombre').distinct()


@login_required
def tasaciones_lista(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver tasaciones.')

    qs = (
        Tasacion.objects.filter(sucursal=request.user.sucursal)
        .select_related('vendedor', 'comision')
        .order_by('-fecha', '-id')
    )
    estado = (request.GET.get('estado') or '').strip()
    if estado in ('confirmada', 'anulada'):
        qs = qs.filter(estado=estado)
    busqueda = (request.GET.get('q') or '').strip()
    if busqueda:
        q = (
            Q(propiedad_nombre__icontains=busqueda)
            | Q(cliente_nombre__icontains=busqueda)
            | Q(vendedor__nombre__icontains=busqueda)
            | Q(vendedor__apellido__icontains=busqueda)
        )
        raw_id = busqueda.lstrip('#').strip()
        if raw_id.isdigit():
            q |= Q(pk=int(raw_id))
        qs = qs.filter(q)

    confirmadas = qs.filter(estado='confirmada')
    totales = confirmadas.aggregate(monto=Sum('monto_ars'), comision=Sum('comision_ars'))
    return render(
        request,
        'inmobiliaria/tasaciones/lista.html',
        {
            'tasaciones': qs[:200],
            'busqueda': busqueda,
            'estado_sel': estado,
            'cantidad': confirmadas.count(),
            'total_monto': totales['monto'] or Decimal('0'),
            'total_comision': totales['comision'] or Decimal('0'),
        },
    )


@login_required
def tasaciones_nueva(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para registrar tasaciones.')

    sucursal = request.user.sucursal
    vendedores = _vendedores_form(sucursal)
    form = _form_vacio(request)
    if request.method == 'POST':
        form = _leer_post(request)
        t = Tasacion(sucursal=sucursal, creado_por=request.user)
        errores = _validar_y_aplicar(form, t, vendedores)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            try:
                with transaction.atomic():
                    t.save()
                    _regenerar_comision(t)
                messages.success(
                    request,
                    f'Tasación #{t.pk} guardada. Comisión de {t.vendedor.apellido}, {t.vendedor.nombre}: '
                    f'${t.comision_ars} acreditada el {t.fecha.strftime("%d/%m/%Y")}.',
                )
                return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la tasación: {exc}')

    return render(
        request,
        'inmobiliaria/tasaciones/form.html',
        {'form': form, 'vendedores': vendedores, 'modo': 'nueva', 'tasacion': None},
    )


@login_required
def tasaciones_editar(request, tasacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para editar tasaciones.')

    sucursal = request.user.sucursal
    t = get_object_or_404(Tasacion, pk=tasacion_id, sucursal=sucursal)
    if t.estado == 'anulada':
        messages.error(request, 'No se puede editar una tasación anulada.')
        return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)
    if _comisiones_de_tasacion(t).filter(estado='pagada').exists():
        messages.error(request, 'No se puede editar: la comisión de esta tasación ya está pagada.')
        return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)

    vendedores = _vendedores_form(sucursal, incluir_id=t.vendedor_id)
    form = _form_desde_tasacion(t)
    if request.method == 'POST':
        form = _leer_post(request)
        errores = _validar_y_aplicar(form, t, vendedores)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            try:
                with transaction.atomic():
                    t.save()
                    _regenerar_comision(t)
                messages.success(
                    request,
                    f'Tasación #{t.pk} actualizada. Comisión regenerada con fecha '
                    f'{t.fecha.strftime("%d/%m/%Y")}.',
                )
                return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la tasación: {exc}')

    return render(
        request,
        'inmobiliaria/tasaciones/form.html',
        {'form': form, 'vendedores': vendedores, 'modo': 'editar', 'tasacion': t},
    )


@login_required
def tasaciones_detalle(request, tasacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver tasaciones.')

    t = get_object_or_404(
        Tasacion.objects.select_related('vendedor', 'comision', 'creado_por', 'sucursal'),
        pk=tasacion_id,
        sucursal=request.user.sucursal,
    )
    comisiones = _comisiones_de_tasacion(t).select_related('vendedor').order_by('id')
    return render(
        request,
        'inmobiliaria/tasaciones/detalle.html',
        {'tasacion': t, 'comisiones': comisiones},
    )


@login_required
def tasaciones_anular(request, tasacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para anular tasaciones.')
    if request.method != 'POST':
        return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=tasacion_id)

    t = get_object_or_404(Tasacion, pk=tasacion_id, sucursal=request.user.sucursal)
    if t.estado == 'anulada':
        messages.info(request, 'La tasación ya estaba anulada.')
        return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)
    with transaction.atomic():
        t.estado = 'anulada'
        t.save(update_fields=['estado', 'actualizado_en'])
        _comisiones_de_tasacion(t).exclude(estado='pagada').update(estado='cancelada')
    messages.warning(request, f'Tasación #{t.pk} anulada. La comisión no pagada quedó cancelada.')
    return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)


@login_required
def tasaciones_eliminar(request, tasacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para eliminar tasaciones.')
    if request.method != 'POST':
        return redirect('inmobiliaria:tasaciones_lista')

    t = get_object_or_404(Tasacion, pk=tasacion_id, sucursal=request.user.sucursal)
    comisiones = _comisiones_de_tasacion(t)
    if comisiones.filter(estado='pagada').exists():
        messages.error(
            request,
            f'No se puede eliminar la tasación #{t.pk}: la comisión ya está pagada. Anulala.',
        )
        return redirect('inmobiliaria:tasaciones_detalle', tasacion_id=t.pk)
    pk = t.pk
    with transaction.atomic():
        t.comision = None
        t.save(update_fields=['comision'])
        comisiones.delete()
        t.delete()
    messages.success(request, f'Tasación #{pk} eliminada junto con su comisión.')
    return redirect('inmobiliaria:tasaciones_lista')
