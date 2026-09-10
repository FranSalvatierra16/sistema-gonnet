"""Sector de ventas cerradas: precio y honorarios en USD; comisión en ARS; sync libro."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

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
    Vendedor,
    VentaPropiedad,
)
from inmobiliaria.models.comision import (
    ROL_COMISION_FICHAJE,
    ROL_COMISION_VENTA,
)
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


def _json_safe(obj):
    return json.dumps(obj, ensure_ascii=False)


def _partir_montos(total, n):
    """Reparte total en n partes (centavos) que suman exacto."""
    total = Decimal(str(total or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if n <= 0:
        return []
    if n == 1:
        return [total]
    base = (total / n).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    partes = [base] * (n - 1)
    partes.append((total - sum(partes)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    return partes


def _leer_montos_comision_post(request, vendedores_sel, cotizacion):
    """
    Montos en USD cargados en el form → se pasan a ARS con la cotización.
    Devuelve partes (vendedor, monto_ars, raw_usd), monto_fichaje_ars, raw_fichaje_usd.
    """
    cotizacion = Decimal(str(cotizacion or 0))
    partes = []
    for vend in vendedores_sel:
        raw = (request.POST.get(f'comision_usd_{vend.id}') or '').strip()
        usd = _parse_decimal(raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if cotizacion > 0 and usd > 0:
            monto_ars = (usd * cotizacion).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        else:
            monto_ars = Decimal('0')
        partes.append((vend, monto_ars, raw))
    fichaje_raw = (request.POST.get('comision_fichaje_usd') or '').strip()
    fichaje_usd = _parse_decimal(fichaje_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if cotizacion > 0 and fichaje_usd > 0:
        fichaje_monto = (fichaje_usd * cotizacion).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    else:
        fichaje_monto = Decimal('0')
    return partes, fichaje_monto, fichaje_raw


@login_required
def operaciones_venta_lista(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver ventas cerradas.')

    sucursal = request.user.sucursal
    qs = (
        OperacionVenta.objects.filter(sucursal=sucursal)
        .select_related('propiedad', 'vendedor', 'fichado_por', 'comision', 'creado_por')
        .prefetch_related('vendedores')
        .order_by('-fecha_venta', '-id')
    )

    estado = (request.GET.get('estado') or '').strip()
    if estado in ('confirmada', 'anulada'):
        qs = qs.filter(estado=estado)

    busqueda = (request.GET.get('q') or '').strip()
    if busqueda:
        q = (
            Q(propiedad_nombre__icontains=busqueda)
            | Q(propiedad__direccion__icontains=busqueda)
            | Q(comprador_nombre__icontains=busqueda)
            | Q(vendedor__nombre__icontains=busqueda)
            | Q(vendedor__apellido__icontains=busqueda)
            | Q(vendedores__nombre__icontains=busqueda)
            | Q(vendedores__apellido__icontains=busqueda)
            | Q(fichado_por__nombre__icontains=busqueda)
            | Q(fichado_por__apellido__icontains=busqueda)
        )
        raw_id = busqueda.lstrip('#').strip()
        if raw_id.isdigit():
            q |= Q(propiedad_id=int(raw_id)) | Q(pk=int(raw_id))
        qs = qs.filter(q).distinct()

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


def _fmt_decimal_form(val):
    """Decimal → texto para inputs (coma decimal)."""
    if val is None or val == '':
        return ''
    try:
        d = Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return ''
    return f'{d:.2f}'.replace('.', ',')


def _form_data_desde_operacion(op):
    """Arma el dict del formulario a partir de una venta existente."""
    vend_ids = [str(v.id) for v in op.lista_vendedores()]
    comisiones_usd = {}
    comision_fichaje_usd = ''
    cot = Decimal(str(op.cotizacion_dolar or 0))
    for c in _comisiones_de_venta(op).exclude(estado='cancelada').select_related('vendedor'):
        ars = Decimal(str(c.monto_comision or 0))
        if cot > 0 and ars > 0:
            usd_txt = _fmt_decimal_form(ars / cot)
        else:
            usd_txt = _fmt_decimal_form(0)
        if c.rol_comision == ROL_COMISION_FICHAJE:
            comision_fichaje_usd = usd_txt
        else:
            comisiones_usd[str(c.vendedor_id)] = usd_txt
    return {
        'fecha_venta': op.fecha_venta.isoformat() if op.fecha_venta else '',
        'precio_usd': _fmt_decimal_form(op.precio_usd),
        'cotizacion_dolar': _fmt_decimal_form(op.cotizacion_dolar),
        'honorarios_usd': _fmt_decimal_form(op.honorarios_usd),
        'honorarios_ars': _fmt_decimal_form(op.honorarios_ars),
        'vendedor_ids': vend_ids,
        'fichado_por_id': str(op.fichado_por_id) if op.fichado_por_id else '',
        'comprador_nombre': op.comprador_nombre or '',
        'escribania': op.escribania or '',
        'observaciones': op.observaciones or '',
        'propiedad_nombre': op.etiqueta_propiedad() if (op.propiedad_nombre or '').strip() or op.propiedad_id else '',
        'comisiones_usd': comisiones_usd,
        'comision_fichaje_usd': comision_fichaje_usd,
    }


def _parsear_post_venta(request, form_data, vendedores, sucursal):
    """
    Valida el POST de alta/edición.
    Devuelve (errores, datos) donde datos tiene propiedad_nombre, fecha, montos, etc.
    """
    errores = []
    propiedad_nombre = (
        form_data.get('propiedad_nombre')
        or request.POST.get('propiedad_nombre')
        or ''
    ).strip()
    if not propiedad_nombre:
        errores.append('Indicá el nombre de la propiedad.')

    try:
        fecha_venta = datetime.strptime(form_data['fecha_venta'][:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        fecha_venta = None
        errores.append('Fecha de venta inválida.')

    precio_usd = _parse_decimal(form_data['precio_usd'])
    cotizacion = _parse_decimal(form_data['cotizacion_dolar'])
    honorarios_usd = _parse_decimal(form_data.get('honorarios_usd'))
    honorarios_ars_raw = (form_data.get('honorarios_ars') or '').strip()
    if honorarios_ars_raw:
        honorarios_ars = _parse_decimal(honorarios_ars_raw).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    elif cotizacion > 0 and honorarios_usd > 0:
        honorarios_ars = (honorarios_usd * cotizacion).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    else:
        honorarios_ars = Decimal('0')

    if precio_usd <= 0:
        errores.append('El precio en USD tiene que ser mayor a 0.')
    if cotizacion <= 0:
        errores.append('Indicá la cotización del dólar (pesos por USD).')
    if honorarios_usd < 0:
        errores.append('Los honorarios de oficina (USD) no pueden ser negativos.')
    if honorarios_ars < 0:
        errores.append('Los honorarios de oficina (ARS) no pueden ser negativos.')

    ids_ok = []
    for raw in form_data['vendedor_ids']:
        if raw.isdigit() and int(raw) not in ids_ok:
            ids_ok.append(int(raw))
    vendedores_sel = list(vendedores.filter(pk__in=ids_ok))
    por_id = {v.id: v for v in vendedores_sel}
    vendedores_sel = [por_id[i] for i in ids_ok if i in por_id]
    if not vendedores_sel:
        errores.append('Seleccioná al menos un vendedor / productor.')

    fichado_por = None
    if form_data['fichado_por_id'].isdigit():
        fichado_por = vendedores.filter(pk=int(form_data['fichado_por_id'])).first()

    partes_ars, monto_fichaje_ars, fichaje_raw = _leer_montos_comision_post(
        request, vendedores_sel, cotizacion
    )
    form_data['comisiones_usd'] = {str(v.id): raw for v, _m, raw in partes_ars}
    form_data['comision_fichaje_usd'] = fichaje_raw

    for vend, monto, _raw in partes_ars:
        if monto < 0:
            errores.append(
                f'La comisión de {vend.apellido}, {vend.nombre} no puede ser negativa.'
            )
    if monto_fichaje_ars < 0:
        errores.append('La comisión de fichaje no puede ser negativa.')
    if fichado_por and monto_fichaje_ars <= 0:
        errores.append('Indicá el monto en USD de la comisión de fichaje.')
    if not fichado_por and monto_fichaje_ars > 0:
        errores.append('Seleccioná quién hizo el fichaje o dejá el monto en 0.')

    total_comisiones_prod = sum((m for _v, m, _r in partes_ars), Decimal('0')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    if total_comisiones_prod <= 0 and not errores:
        errores.append('Cargá al menos una comisión de productor en USD.')

    return errores, {
        'propiedad_nombre': propiedad_nombre[:255],
        'fecha_venta': fecha_venta,
        'precio_usd': precio_usd,
        'cotizacion': cotizacion,
        'vendedores_sel': vendedores_sel,
        'fichado_por': fichado_por,
        'partes_ars': partes_ars,
        'monto_fichaje_ars': monto_fichaje_ars,
        'honorarios_ars': honorarios_ars,
        'honorarios_usd': honorarios_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
    }


def _aplicar_json_form(form_data):
    form_data['comisiones_usd_json'] = _json_safe(form_data.get('comisiones_usd') or {})
    form_data['comision_fichaje_usd_json'] = _json_safe(
        form_data.get('comision_fichaje_usd') or ''
    )
    return form_data


def _reemplazar_comisiones_venta(op, partes_ars, monto_fichaje_ars, fichado_por):
    """Borra comisiones no pagadas de la venta y vuelve a crearlas."""
    qs = _comisiones_de_venta(op)
    if qs.filter(estado='pagada').exists():
        raise ValueError(
            'Hay comisiones ya pagadas vinculadas a esta venta; no se pueden regenerar.'
        )
    qs.delete()
    op.comision = None
    op.save(update_fields=['comision'])
    comisiones = _crear_comisiones_venta(
        op,
        [(v, m) for v, m, *_rest in partes_ars],
        monto_fichaje_ars if fichado_por else Decimal('0'),
    )
    if comisiones:
        op.comision = comisiones[0]
        op.save(update_fields=['comision'])
    return comisiones


def _liberar_marca_vendida_si_corresponde(propiedad_id):
    """Si no quedan ventas confirmadas de esa ficha, vuelve a disponible."""
    if not propiedad_id:
        return
    otras = OperacionVenta.objects.filter(
        propiedad_id=propiedad_id, estado='confirmada'
    ).exists()
    if otras:
        return
    info = VentaPropiedad.objects.filter(propiedad_id=propiedad_id).first()
    if info and info.estado == 'vendido':
        info.estado = 'disponible'
        info.en_venta = True
        info.save(update_fields=['estado', 'en_venta', 'fecha_actualizacion'])


@login_required
def operaciones_venta_nueva(request):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para registrar ventas.')

    sucursal = request.user.sucursal
    vendedores = Vendedor.objects.filter(
        sucursal=sucursal, is_active=True
    ).order_by('apellido', 'nombre')

    default_vendedor = str(request.user.pk) if isinstance(request.user, Vendedor) else ''
    form_data = {
        'fecha_venta': timezone.localdate().isoformat(),
        'precio_usd': '',
        'cotizacion_dolar': '',
        'honorarios_usd': '',
        'honorarios_ars': '',
        'vendedor_ids': [default_vendedor] if default_vendedor else [],
        'fichado_por_id': '',
        'comprador_nombre': '',
        'escribania': '',
        'observaciones': '',
        'propiedad_nombre': '',
        'comisiones_usd': {},
        'comision_fichaje_usd': '',
    }

    if request.method == 'POST':
        vendedor_ids_raw = request.POST.getlist('vendedor_ids')
        form_data.update({
            'fecha_venta': (request.POST.get('fecha_venta') or '').strip(),
            'precio_usd': (request.POST.get('precio_usd') or '').strip(),
            'cotizacion_dolar': (request.POST.get('cotizacion_dolar') or '').strip(),
            'honorarios_usd': (request.POST.get('honorarios_usd') or '').strip(),
            'honorarios_ars': (request.POST.get('honorarios_ars') or '').strip(),
            'vendedor_ids': [x.strip() for x in vendedor_ids_raw if (x or '').strip()],
            'fichado_por_id': (request.POST.get('fichado_por_id') or '').strip(),
            'comprador_nombre': (request.POST.get('comprador_nombre') or '').strip(),
            'escribania': (request.POST.get('escribania') or '').strip(),
            'observaciones': (request.POST.get('observaciones') or '').strip(),
            'propiedad_nombre': (request.POST.get('propiedad_nombre') or '').strip(),
            'comision_fichaje_usd': (request.POST.get('comision_fichaje_usd') or '').strip(),
        })
        errores, datos = _parsear_post_venta(request, form_data, vendedores, sucursal)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            try:
                with transaction.atomic():
                    op = OperacionVenta(
                        propiedad=None,
                        propiedad_nombre=datos['propiedad_nombre'],
                        sucursal=sucursal,
                        vendedor=datos['vendedores_sel'][0],
                        fichado_por=datos['fichado_por'],
                        fecha_venta=datos['fecha_venta'],
                        precio_usd=datos['precio_usd'].quantize(Decimal('0.01')),
                        cotizacion_dolar=datos['cotizacion'].quantize(Decimal('0.0001')),
                        honorarios_usd=datos['honorarios_usd'],
                        honorarios_ars=datos['honorarios_ars'],
                        gastos_escritura_usd=Decimal('0'),
                        comprador_nombre=form_data['comprador_nombre'][:255],
                        escribania=form_data['escribania'][:255],
                        observaciones=form_data['observaciones'],
                        estado='confirmada',
                        creado_por=request.user,
                    )
                    op.save()
                    op.vendedores.set(datos['vendedores_sel'])
                    comisiones = _crear_comisiones_venta(
                        op,
                        [(v, m) for v, m, _r in datos['partes_ars']],
                        datos['monto_fichaje_ars']
                        if datos['fichado_por']
                        else Decimal('0'),
                    )
                    if comisiones:
                        op.comision = comisiones[0]
                        op.save(update_fields=['comision'])
                messages.success(
                    request,
                    f'Venta #{op.pk} registrada: U$S {op.precio_usd} — '
                    f'honorarios oficina U$S {op.honorarios_usd} / ${op.honorarios_ars} '
                    f'(cotiz. {op.cotizacion_dolar}).',
                )
                return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la venta: {exc}')

    _aplicar_json_form(form_data)
    return render(
        request,
        'inmobiliaria/ventas/operacion_form.html',
        {
            'vendedores': vendedores,
            'form': form_data,
            'modo': 'nueva',
            'operacion': None,
        },
    )


@login_required
def operaciones_venta_editar(request, operacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para editar ventas.')

    sucursal = request.user.sucursal
    op = get_object_or_404(
        OperacionVenta.objects.select_related(
            'propiedad',
            'propiedad__propietario',
            'fichado_por',
            'vendedor',
            'comision',
        ).prefetch_related('vendedores'),
        pk=operacion_id,
        sucursal=sucursal,
    )
    if op.estado == 'anulada':
        messages.error(request, 'No se puede editar una venta anulada. Eliminala o cargá una nueva.')
        return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)

    if _comisiones_de_venta(op).filter(estado='pagada').exists():
        messages.error(
            request,
            'No se puede editar: hay comisiones ya pagadas vinculadas a esta venta.',
        )
        return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)

    # Incluir vendedores de la venta aunque estén inactivos.
    ids_venta = list(op.vendedores.values_list('id', flat=True))
    if op.vendedor_id and op.vendedor_id not in ids_venta:
        ids_venta.append(op.vendedor_id)
    if op.fichado_por_id and op.fichado_por_id not in ids_venta:
        ids_venta.append(op.fichado_por_id)
    vendedores = Vendedor.objects.filter(
        Q(sucursal=sucursal, is_active=True) | Q(pk__in=ids_venta)
    ).order_by('apellido', 'nombre').distinct()

    form_data = _form_data_desde_operacion(op)

    if request.method == 'POST':
        vendedor_ids_raw = request.POST.getlist('vendedor_ids')
        form_data.update({
            'fecha_venta': (request.POST.get('fecha_venta') or '').strip(),
            'precio_usd': (request.POST.get('precio_usd') or '').strip(),
            'cotizacion_dolar': (request.POST.get('cotizacion_dolar') or '').strip(),
            'honorarios_usd': (request.POST.get('honorarios_usd') or '').strip(),
            'honorarios_ars': (request.POST.get('honorarios_ars') or '').strip(),
            'vendedor_ids': [x.strip() for x in vendedor_ids_raw if (x or '').strip()],
            'fichado_por_id': (request.POST.get('fichado_por_id') or '').strip(),
            'comprador_nombre': (request.POST.get('comprador_nombre') or '').strip(),
            'escribania': (request.POST.get('escribania') or '').strip(),
            'observaciones': (request.POST.get('observaciones') or '').strip(),
            'propiedad_nombre': (request.POST.get('propiedad_nombre') or '').strip(),
            'comision_fichaje_usd': (request.POST.get('comision_fichaje_usd') or '').strip(),
        })
        errores, datos = _parsear_post_venta(request, form_data, vendedores, sucursal)
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            prop_anterior_id = op.propiedad_id
            try:
                with transaction.atomic():
                    op.propiedad = None
                    op.propiedad_nombre = datos['propiedad_nombre']
                    op.vendedor = datos['vendedores_sel'][0]
                    op.fichado_por = datos['fichado_por']
                    op.fecha_venta = datos['fecha_venta']
                    op.precio_usd = datos['precio_usd'].quantize(Decimal('0.01'))
                    op.cotizacion_dolar = datos['cotizacion'].quantize(Decimal('0.0001'))
                    op.honorarios_usd = datos['honorarios_usd']
                    op.honorarios_ars = datos['honorarios_ars']
                    op.gastos_escritura_usd = Decimal('0')
                    op.comprador_nombre = form_data['comprador_nombre'][:255]
                    op.escribania = form_data['escribania'][:255]
                    op.observaciones = form_data['observaciones']
                    op.estado = 'confirmada'
                    op.save()
                    op.vendedores.set(datos['vendedores_sel'])
                    if prop_anterior_id:
                        _liberar_marca_vendida_si_corresponde(prop_anterior_id)
                    _reemplazar_comisiones_venta(
                        op,
                        datos['partes_ars'],
                        datos['monto_fichaje_ars'],
                        datos['fichado_por'],
                    )
                messages.success(
                    request,
                    f'Venta #{op.pk} actualizada. Comisiones regeneradas con fecha '
                    f'{op.fecha_venta.strftime("%d/%m/%Y")}.',
                )
                return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la venta: {exc}')

    _aplicar_json_form(form_data)
    return render(
        request,
        'inmobiliaria/ventas/operacion_form.html',
        {
            'vendedores': vendedores,
            'form': form_data,
            'modo': 'editar',
            'operacion': op,
        },
    )


@login_required
def operaciones_venta_detalle(request, operacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para ver ventas.')

    op = get_object_or_404(
        OperacionVenta.objects.select_related(
            'propiedad',
            'propiedad__propietario',
            'vendedor',
            'fichado_por',
            'comision',
            'creado_por',
            'sucursal',
        ).prefetch_related('vendedores'),
        pk=operacion_id,
        sucursal=request.user.sucursal,
    )
    comisiones = ComisionVendedor.objects.filter(
        observaciones__contains=f'Operación venta #{op.pk}'
    ).select_related('vendedor').order_by('id')
    return render(
        request,
        'inmobiliaria/ventas/operacion_detalle.html',
        {'operacion': op, 'comisiones': comisiones},
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
        ComisionVendedor.objects.filter(
            observaciones__contains=f'Operación venta #{op.pk}',
        ).exclude(estado='pagada').update(estado='cancelada')
    messages.warning(request, f'Venta #{op.pk} anulada. Las comisiones no pagadas quedaron canceladas.')
    return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)


def _comisiones_de_venta(op):
    qs = ComisionVendedor.objects.filter(
        observaciones__contains=f'Operación venta #{op.pk}',
    )
    if op.comision_id:
        qs = ComisionVendedor.objects.filter(
            Q(pk=op.comision_id) | Q(observaciones__contains=f'Operación venta #{op.pk}')
        )
    return qs


@login_required
def operaciones_venta_eliminar(request, operacion_id):
    if not _puede_gestionar_ventas(request.user):
        return HttpResponseForbidden('No tenés permiso para eliminar ventas.')
    if request.method != 'POST':
        return redirect('inmobiliaria:operaciones_venta_lista')

    op = get_object_or_404(
        OperacionVenta.objects.select_related('comision', 'propiedad'),
        pk=operacion_id,
        sucursal=request.user.sucursal,
    )
    prop_id = op.propiedad_id
    op_pk = op.pk

    comisiones = _comisiones_de_venta(op)
    if comisiones.filter(estado='pagada').exists():
        messages.error(
            request,
            f'No se puede eliminar la venta #{op_pk}: hay comisiones ya pagadas. '
            'Anulala o resolvé esas comisiones primero.',
        )
        return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op_pk)

    with transaction.atomic():
        comisiones.delete()
        op.comision = None
        op.save(update_fields=['comision'])
        op.delete()
        _liberar_marca_vendida_si_corresponde(prop_id)

    messages.success(
        request,
        f'Venta #{op_pk} eliminada. Se quitaron las comisiones asociadas.',
    )
    return redirect('inmobiliaria:operaciones_venta_lista')


def _marcar_propiedad_vendida(propiedad):
    if not propiedad:
        return
    info, _ = VentaPropiedad.objects.get_or_create(propiedad=propiedad)
    info.estado = 'vendido'
    info.en_venta = False
    info.save(update_fields=['estado', 'en_venta', 'fecha_actualizacion'])


def _sincronizar_libro_propiedad(op, usuario=None):
    """
    Refleja la venta en CostosCompraLibroPropiedad (libro del depto en oficina /
    mis propiedades): valor vendido, escritura, honorarios y escribanía.
    Solo aplica si la venta sigue vinculada a una ficha.
    """
    if not op.propiedad_id:
        return
    costos, _ = CostosCompraLibroPropiedad.objects.get_or_create(propiedad=op.propiedad)
    costos.valor_depto_vendido = op.precio_usd
    costos.gastos_escritura_venta = op.gastos_escritura_usd or Decimal('0')
    costos.honorarios_venta = op.honorarios_usd or Decimal('0')
    if op.escribania:
        costos.escribania = op.escribania[:255]
    if usuario is not None:
        costos.actualizado_por = usuario
    costos.save()


def _fecha_operacion_aware(fecha_venta):
    """Medianoche local del día de venta (misma convención que alquileres)."""
    from datetime import time

    dt = datetime.combine(fecha_venta, time.min)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _estado_comision_venta(fecha_venta):
    """Venta cerrada: la comisión se acredita al registrar, con fecha = día de venta."""
    return 'confirmada'


def _crear_comisiones_venta(op, partes_ars, monto_fichaje_ars=None):
    """
    Crea comisiones con los montos ARS cargados a mano en el formulario.
    ``partes_ars``: lista de (vendedor, monto_ars).
    No modifica honorarios de oficina de la operación (van aparte).
    El % guardado es (monto comisión / honorarios oficina ARS) × 100.
    """
    partes_ars = [(v, Decimal(str(m or 0))) for v, m in (partes_ars or [])]
    cot = Decimal(str(op.cotizacion_dolar or 0))
    honorarios_base = Decimal(str(op.honorarios_ars or 0)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )

    dt = _fecha_operacion_aware(op.fecha_venta)
    estado_com = _estado_comision_venta(op.fecha_venta)
    dir_prop = op.etiqueta_propiedad()
    creadas = []

    def _pct_sobre_honorarios(monto):
        if honorarios_base <= 0 or monto <= 0:
            return Decimal('0')
        return ((monto / honorarios_base) * Decimal('100')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    for vend, monto in partes_ars:
        if monto <= 0:
            continue
        usd_parte = (monto / cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cot else Decimal('0')
        pct_comision = _pct_sobre_honorarios(monto)
        creadas.append(
            ComisionVendedor.objects.create(
                vendedor=vend,
                monto_total_operacion=honorarios_base or monto,
                porcentaje_comision=pct_comision,
                monto_comision=monto,
                concepto_operacion=(
                    f'Venta — {dir_prop} '
                    f'(U$S {op.precio_usd} @ {op.cotizacion_dolar})'
                )[:200],
                rol_comision=ROL_COMISION_VENTA,
                fecha_operacion=dt,
                estado=estado_com,
                observaciones=(
                    f'Operación venta #{op.pk}. Comisión cargada: ${monto} ARS '
                    f'(equiv. U$S {usd_parte} @ cotiz. {op.cotizacion_dolar}; '
                    f'{pct_comision}% de honorarios oficina ${honorarios_base}).'
                ),
            )
        )

    monto_f = Decimal(str(monto_fichaje_ars or 0)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    fichado = op.fichado_por
    if fichado and monto_f > 0:
        usd_f = (monto_f / cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cot else Decimal('0')
        pct_f = _pct_sobre_honorarios(monto_f)
        creadas.append(
            ComisionVendedor.objects.create(
                vendedor=fichado,
                monto_total_operacion=honorarios_base or monto_f,
                porcentaje_comision=pct_f,
                monto_comision=monto_f,
                concepto_operacion=(
                    f'Fichaje venta — {dir_prop}'
                )[:200],
                rol_comision=ROL_COMISION_FICHAJE,
                fecha_operacion=dt,
                estado=estado_com,
                observaciones=(
                    f'Operación venta #{op.pk}. Fichaje cargado: ${monto_f} ARS '
                    f'(equiv. U$S {usd_f}; {pct_f}% de honorarios oficina ${honorarios_base}).'
                ),
            )
        )

    return creadas
