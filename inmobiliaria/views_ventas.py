"""Sector de ventas cerradas: precio y honorarios en USD; comisión en ARS; sync libro."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inmobiliaria.decimal_utils import parse_decimal_monto
from inmobiliaria.models import (
    ComisionVendedor,
    CostosCompraLibroPropiedad,
    OperacionVenta,
    Propiedad,
    Vendedor,
    VentaPropiedad,
)
from inmobiliaria.models.comision import ROL_COMISION_VENTA
from inmobiliaria.models.persona import usuario_es_nivel_administracion


def _parse_decimal(valor, default='0'):
    try:
        return parse_decimal_monto(valor)
    except Exception:
        try:
            return Decimal(str(valor or default).replace(',', '.'))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal(default)


def _puede_gestionar_ventas(user):
    if not user or not user.is_authenticated:
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return usuario_es_nivel_administracion(user) or getattr(user, 'nivel', 0) >= 3


@login_required
def operaciones_venta_lista(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver ventas cerradas.')

    sucursal = request.user.sucursal
    qs = (
        OperacionVenta.objects.filter(sucursal=sucursal)
        .select_related('propiedad', 'vendedor', 'comision', 'creado_por')
        .order_by('-fecha_venta', '-id')
    )

    estado = (request.GET.get('estado') or '').strip()
    if estado in ('confirmada', 'anulada'):
        qs = qs.filter(estado=estado)

    busqueda = (request.GET.get('q') or '').strip()
    if busqueda:
        q = (
            Q(propiedad__direccion__icontains=busqueda)
            | Q(comprador_nombre__icontains=busqueda)
            | Q(vendedor__nombre__icontains=busqueda)
            | Q(vendedor__apellido__icontains=busqueda)
        )
        raw_id = busqueda.lstrip('#').strip()
        if raw_id.isdigit():
            q |= Q(propiedad_id=int(raw_id)) | Q(pk=int(raw_id))
        qs = qs.filter(q)

    confirmadas = qs.filter(estado='confirmada')
    totales = confirmadas.aggregate(
        total_usd=Sum('precio_usd'),
        total_honorarios_usd=Sum('honorarios_usd'),
        total_honorarios_ars=Sum('honorarios_ars'),
    )

    return render(
        request,
        'inmobiliaria/ventas/operaciones_lista.html',
        {
            'operaciones': qs[:200],
            'busqueda': busqueda,
            'estado_sel': estado,
            'total_usd': totales['total_usd'] or Decimal('0'),
            'total_honorarios_usd': totales['total_honorarios_usd'] or Decimal('0'),
            'total_honorarios': totales['total_honorarios_ars'] or Decimal('0'),
            'cantidad': confirmadas.count(),
        },
    )


@login_required
def operaciones_venta_nueva(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para registrar ventas.')

    sucursal = request.user.sucursal
    vendedores = Vendedor.objects.filter(
        sucursal=sucursal, is_active=True
    ).order_by('apellido', 'nombre')

    propiedad_pre = None
    prop_id = (request.GET.get('propiedad') or request.POST.get('propiedad_id') or '').strip()
    if prop_id.isdigit():
        propiedad_pre = Propiedad.objects.filter(
            pk=int(prop_id), sucursal=sucursal
        ).select_related('propietario', 'info_venta', 'costos_compra_libro').first()

    form_data = {
        'fecha_venta': timezone.localdate().isoformat(),
        'precio_usd': '',
        'cotizacion_dolar': '',
        'honorarios_usd': '',
        'gastos_escritura_usd': '',
        'vendedor_id': str(request.user.pk) if isinstance(request.user, Vendedor) else '',
        'comprador_nombre': '',
        'escribania': '',
        'observaciones': '',
        'propiedad_buscar': '',
    }
    if propiedad_pre:
        form_data['propiedad_buscar'] = (
            f'#{propiedad_pre.id} — {(propiedad_pre.direccion or "").strip()}'
        )
        info = getattr(propiedad_pre, 'info_venta', None)
        if info and info.precio_venta:
            form_data['precio_usd'] = str(info.precio_venta)
        costos = getattr(propiedad_pre, 'costos_compra_libro', None)
        if costos:
            if costos.valor_depto_vendido:
                form_data['precio_usd'] = str(costos.valor_depto_vendido)
            if costos.honorarios_venta:
                form_data['honorarios_usd'] = str(costos.honorarios_venta)
            if costos.gastos_escritura_venta:
                form_data['gastos_escritura_usd'] = str(costos.gastos_escritura_venta)
            if costos.escribania:
                form_data['escribania'] = costos.escribania

    if request.method == 'POST':
        form_data.update({
            'fecha_venta': (request.POST.get('fecha_venta') or '').strip(),
            'precio_usd': (request.POST.get('precio_usd') or '').strip(),
            'cotizacion_dolar': (request.POST.get('cotizacion_dolar') or '').strip(),
            'honorarios_usd': (request.POST.get('honorarios_usd') or '').strip(),
            'gastos_escritura_usd': (request.POST.get('gastos_escritura_usd') or '').strip(),
            'vendedor_id': (request.POST.get('vendedor_id') or '').strip(),
            'comprador_nombre': (request.POST.get('comprador_nombre') or '').strip(),
            'escribania': (request.POST.get('escribania') or '').strip(),
            'observaciones': (request.POST.get('observaciones') or '').strip(),
            'propiedad_buscar': (request.POST.get('propiedad_buscar') or '').strip(),
        })
        prop_id = (request.POST.get('propiedad_id') or '').strip()
        errores = []

        propiedad = None
        if prop_id.isdigit():
            propiedad = Propiedad.objects.filter(
                pk=int(prop_id), sucursal=sucursal
            ).first()
        if not propiedad:
            errores.append('Seleccioná una propiedad válida de la sucursal.')

        try:
            fecha_venta = datetime.strptime(form_data['fecha_venta'][:10], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            fecha_venta = None
            errores.append('Fecha de venta inválida.')

        precio_usd = _parse_decimal(form_data['precio_usd'])
        cotizacion = _parse_decimal(form_data['cotizacion_dolar'])
        honorarios_usd = _parse_decimal(form_data['honorarios_usd'])
        gastos_escritura = _parse_decimal(form_data['gastos_escritura_usd'])
        if precio_usd <= 0:
            errores.append('El precio en USD tiene que ser mayor a 0.')
        if cotizacion <= 0:
            errores.append('Indicá la cotización del dólar (pesos por USD).')
        if honorarios_usd < 0:
            errores.append('Los honorarios no pueden ser negativos.')
        if gastos_escritura < 0:
            errores.append('Los gastos de escritura no pueden ser negativos.')

        vendedor = None
        if form_data['vendedor_id'].isdigit():
            vendedor = vendedores.filter(pk=int(form_data['vendedor_id'])).first()
        if not vendedor:
            errores.append('Seleccioná el vendedor que realizó la venta.')

        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            honorarios_ars = (honorarios_usd * cotizacion).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            try:
                with transaction.atomic():
                    op = OperacionVenta(
                        propiedad=propiedad,
                        sucursal=sucursal,
                        vendedor=vendedor,
                        fecha_venta=fecha_venta,
                        precio_usd=precio_usd.quantize(Decimal('0.01')),
                        cotizacion_dolar=cotizacion.quantize(Decimal('0.0001')),
                        honorarios_usd=honorarios_usd.quantize(Decimal('0.01')),
                        honorarios_ars=honorarios_ars,
                        gastos_escritura_usd=gastos_escritura.quantize(Decimal('0.01')),
                        comprador_nombre=form_data['comprador_nombre'][:255],
                        escribania=form_data['escribania'][:255],
                        observaciones=form_data['observaciones'],
                        estado='confirmada',
                        creado_por=request.user,
                    )
                    op.save()
                    _marcar_propiedad_vendida(propiedad)
                    _sincronizar_libro_propiedad(op, usuario=request.user)
                    if honorarios_ars > 0:
                        comision = _crear_comision_venta(op)
                        op.comision = comision
                        op.save(update_fields=['comision'])
                messages.success(
                    request,
                    f'Venta #{op.pk} registrada: U$S {op.precio_usd} — '
                    f'honorarios U$S {op.honorarios_usd} → ${op.honorarios_ars} '
                    f'(cotiz. {op.cotizacion_dolar}). Libro del depto actualizado.',
                )
                return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la venta: {exc}')

        if prop_id.isdigit():
            propiedad_pre = Propiedad.objects.filter(
                pk=int(prop_id), sucursal=sucursal
            ).select_related('propietario').first()

    return render(
        request,
        'inmobiliaria/ventas/operacion_form.html',
        {
            'vendedores': vendedores,
            'propiedad': propiedad_pre,
            'form': form_data,
            'modo': 'nueva',
        },
    )


@login_required
def operaciones_venta_detalle(request, operacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver ventas.')

    op = get_object_or_404(
        OperacionVenta.objects.select_related(
            'propiedad', 'propiedad__propietario', 'vendedor', 'comision', 'creado_por', 'sucursal'
        ),
        pk=operacion_id,
        sucursal=request.user.sucursal,
    )
    return render(
        request,
        'inmobiliaria/ventas/operacion_detalle.html',
        {'operacion': op},
    )


@login_required
def operaciones_venta_anular(request, operacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para anular ventas.')
    if request.method != 'POST':
        return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=operacion_id)

    op = get_object_or_404(
        OperacionVenta.objects.select_related('comision', 'propiedad'),
        pk=operacion_id,
        sucursal=request.user.sucursal,
    )
    if op.estado == 'anulada':
        messages.info(request, 'La venta ya estaba anulada.')
        return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)

    with transaction.atomic():
        op.estado = 'anulada'
        op.save(update_fields=['estado', 'actualizado_en'])
        if op.comision_id and op.comision.estado != 'pagada':
            op.comision.estado = 'cancelada'
            op.comision.save(update_fields=['estado'])
        # No reabrimos la propiedad ni borramos el libro: queda a criterio del usuario.
    messages.warning(request, f'Venta #{op.pk} anulada. La comisión quedó cancelada (si no estaba pagada).')
    return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)


def _marcar_propiedad_vendida(propiedad):
    info, _ = VentaPropiedad.objects.get_or_create(propiedad=propiedad)
    info.estado = 'vendido'
    info.en_venta = False
    info.save(update_fields=['estado', 'en_venta', 'fecha_actualizacion'])


def _sincronizar_libro_propiedad(op, usuario=None):
    """
    Refleja la venta en CostosCompraLibroPropiedad (libro del depto en oficina /
    mis propiedades): valor vendido, escritura, honorarios y escribanía.
    """
    costos, _ = CostosCompraLibroPropiedad.objects.get_or_create(propiedad=op.propiedad)
    costos.valor_depto_vendido = op.precio_usd
    costos.gastos_escritura_venta = op.gastos_escritura_usd or Decimal('0')
    costos.honorarios_venta = op.honorarios_usd or Decimal('0')
    if op.escribania:
        costos.escribania = op.escribania[:255]
    if usuario is not None:
        costos.actualizado_por = usuario
    costos.save()


def _crear_comision_venta(op):
    """Comisión en pesos = honorarios USD × cotización."""
    precio_ars = (op.precio_usd * op.cotizacion_dolar).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    pct = Decimal('0')
    if precio_ars > 0 and op.honorarios_ars > 0:
        pct = ((op.honorarios_ars / precio_ars) * Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    dt = datetime.combine(op.fecha_venta, datetime.min.time())
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())

    dir_prop = (op.propiedad.direccion or '').strip() or f'#{op.propiedad_id}'
    return ComisionVendedor.objects.create(
        vendedor=op.vendedor,
        monto_total_operacion=precio_ars,
        porcentaje_comision=pct,
        monto_comision=op.honorarios_ars,
        concepto_operacion=(
            f'Venta propiedad #{op.propiedad_id} — {dir_prop} '
            f'(U$S {op.precio_usd} @ {op.cotizacion_dolar})'
        )[:200],
        rol_comision=ROL_COMISION_VENTA,
        fecha_operacion=dt,
        estado='pendiente',
        observaciones=(
            f'Operación venta #{op.pk}. Honorarios U$S {op.honorarios_usd} '
            f'× cotiz. {op.cotizacion_dolar} = ${op.honorarios_ars} ARS.'
        ),
    )
