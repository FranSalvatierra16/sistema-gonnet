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
    Propiedad,
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


def _etiqueta_propiedad(prop):
    if not prop:
        return ''
    partes = [f'#{prop.id}', '—', (prop.direccion or '').strip() or 'Sin dirección']
    piso = (getattr(prop, 'piso', None) or '').strip()
    depto = (getattr(prop, 'departamento', None) or '').strip()
    if piso or depto:
        ud = ' '.join(x for x in [f'{piso}°' if piso else '', depto] if x).strip()
        if ud:
            partes.append(f'· {ud}')
    prop_txt = ''
    if prop.propietario:
        prop_txt = (
            getattr(prop.propietario, 'nombre_completo_propietario', lambda: '')()
            or str(prop.propietario)
        ).strip()
        if prop_txt:
            partes.append(f'· {prop_txt}')
    return ' '.join(partes)


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


def _leer_montos_comision_post(request, vendedores_sel):
    """Montos ARS cargados a mano en el form: productores + fichaje."""
    partes = []
    for vend in vendedores_sel:
        raw = (request.POST.get(f'comision_ars_{vend.id}') or '').strip()
        monto = _parse_decimal(raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        partes.append((vend, monto, raw))
    fichaje_raw = (request.POST.get('comision_fichaje_ars') or '').strip()
    fichaje_monto = _parse_decimal(fichaje_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
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
            Q(propiedad__direccion__icontains=busqueda)
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
        ).select_related('propietario', 'info_venta', 'costos_compra_libro', 'fichado_por').first()

    default_vendedor = str(request.user.pk) if isinstance(request.user, Vendedor) else ''
    form_data = {
        'fecha_venta': timezone.localdate().isoformat(),
        'precio_usd': '',
        'cotizacion_dolar': '',
        'honorarios_usd': '',
        'gastos_escritura_usd': '',
        'vendedor_ids': [default_vendedor] if default_vendedor else [],
        'fichado_por_id': '',
        'comprador_nombre': '',
        'escribania': '',
        'observaciones': '',
        'propiedad_buscar': '',
        'comisiones_ars': {},
        'comision_fichaje_ars': '',
    }
    if propiedad_pre:
        form_data['propiedad_buscar'] = _etiqueta_propiedad(propiedad_pre)
        if propiedad_pre.fichado_por_id:
            form_data['fichado_por_id'] = str(propiedad_pre.fichado_por_id)
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
        vendedor_ids_raw = request.POST.getlist('vendedor_ids')
        form_data.update({
            'fecha_venta': (request.POST.get('fecha_venta') or '').strip(),
            'precio_usd': (request.POST.get('precio_usd') or '').strip(),
            'cotizacion_dolar': (request.POST.get('cotizacion_dolar') or '').strip(),
            'honorarios_usd': (request.POST.get('honorarios_usd') or '').strip(),
            'gastos_escritura_usd': (request.POST.get('gastos_escritura_usd') or '').strip(),
            'vendedor_ids': [x.strip() for x in vendedor_ids_raw if (x or '').strip()],
            'fichado_por_id': (request.POST.get('fichado_por_id') or '').strip(),
            'comprador_nombre': (request.POST.get('comprador_nombre') or '').strip(),
            'escribania': (request.POST.get('escribania') or '').strip(),
            'observaciones': (request.POST.get('observaciones') or '').strip(),
            'propiedad_buscar': (request.POST.get('propiedad_buscar') or '').strip(),
            'comision_fichaje_ars': (request.POST.get('comision_fichaje_ars') or '').strip(),
        })
        prop_id = (request.POST.get('propiedad_id') or '').strip()
        errores = []

        propiedad = None
        if prop_id.isdigit():
            propiedad = Propiedad.objects.filter(
                pk=int(prop_id), sucursal=sucursal
            ).select_related('fichado_por').first()
        if not propiedad:
            errores.append('Seleccioná una propiedad válida de la sucursal.')

        try:
            fecha_venta = datetime.strptime(form_data['fecha_venta'][:10], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            fecha_venta = None
            errores.append('Fecha de venta inválida.')

        precio_usd = _parse_decimal(form_data['precio_usd'])
        cotizacion = _parse_decimal(form_data['cotizacion_dolar'])
        gastos_escritura = _parse_decimal(form_data['gastos_escritura_usd'])
        if precio_usd <= 0:
            errores.append('El precio en USD tiene que ser mayor a 0.')
        if cotizacion <= 0:
            errores.append('Indicá la cotización del dólar (pesos por USD).')
        if gastos_escritura < 0:
            errores.append('Los gastos de escritura no pueden ser negativos.')

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
            request, vendedores_sel
        )
        form_data['comisiones_ars'] = {
            str(v.id): raw for v, _m, raw in partes_ars
        }
        form_data['comision_fichaje_ars'] = fichaje_raw

        for vend, monto, _raw in partes_ars:
            if monto < 0:
                errores.append(
                    f'La comisión de {vend.apellido}, {vend.nombre} no puede ser negativa.'
                )
        if monto_fichaje_ars < 0:
            errores.append('La comisión de fichaje no puede ser negativa.')
        if fichado_por and monto_fichaje_ars <= 0:
            errores.append('Indicá el monto en pesos de la comisión de fichaje.')
        if not fichado_por and monto_fichaje_ars > 0:
            errores.append('Seleccioná quién hizo el fichaje o dejá el monto en 0.')

        honorarios_ars = sum((m for _v, m, _r in partes_ars), Decimal('0')).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        if honorarios_ars <= 0 and not errores:
            errores.append('Cargá al menos una comisión de productor en pesos.')

        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            honorarios_usd = (honorarios_ars / cotizacion).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            try:
                with transaction.atomic():
                    op = OperacionVenta(
                        propiedad=propiedad,
                        sucursal=sucursal,
                        vendedor=vendedores_sel[0],
                        fichado_por=fichado_por,
                        fecha_venta=fecha_venta,
                        precio_usd=precio_usd.quantize(Decimal('0.01')),
                        cotizacion_dolar=cotizacion.quantize(Decimal('0.0001')),
                        honorarios_usd=honorarios_usd,
                        honorarios_ars=honorarios_ars,
                        gastos_escritura_usd=gastos_escritura.quantize(Decimal('0.01')),
                        comprador_nombre=form_data['comprador_nombre'][:255],
                        escribania=form_data['escribania'][:255],
                        observaciones=form_data['observaciones'],
                        estado='confirmada',
                        creado_por=request.user,
                    )
                    op.save()
                    op.vendedores.set(vendedores_sel)
                    _marcar_propiedad_vendida(propiedad)
                    _sincronizar_libro_propiedad(op, usuario=request.user)
                    comisiones = _crear_comisiones_venta(
                        op,
                        [(v, m) for v, m, _r in partes_ars],
                        monto_fichaje_ars if fichado_por else Decimal('0'),
                    )
                    if comisiones:
                        op.comision = comisiones[0]
                        op.save(update_fields=['comision'])
                messages.success(
                    request,
                    f'Venta #{op.pk} registrada: U$S {op.precio_usd} — '
                    f'comisiones productores ${op.honorarios_ars} '
                    f'(U$S {op.honorarios_usd} @ cotiz. {op.cotizacion_dolar}). '
                    f'Libro del depto actualizado.',
                )
                return redirect('inmobiliaria:operaciones_venta_detalle', operacion_id=op.pk)
            except Exception as exc:
                messages.error(request, f'No se pudo guardar la venta: {exc}')

        if prop_id.isdigit():
            propiedad_pre = Propiedad.objects.filter(
                pk=int(prop_id), sucursal=sucursal
            ).select_related('propietario', 'fichado_por').first()

    form_data['comisiones_ars_json'] = _json_safe(form_data.get('comisiones_ars') or {})
    form_data['comision_fichaje_ars_json'] = _json_safe(
        form_data.get('comision_fichaje_ars') or ''
    )

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

        # Si no quedan ventas confirmadas de esa propiedad, sacar marca de vendido.
        otras = OperacionVenta.objects.filter(
            propiedad_id=prop_id, estado='confirmada'
        ).exists()
        if not otras:
            info = VentaPropiedad.objects.filter(propiedad_id=prop_id).first()
            if info and info.estado == 'vendido':
                info.estado = 'disponible'
                info.en_venta = True
                info.save(update_fields=['estado', 'en_venta', 'fecha_actualizacion'])

    messages.success(
        request,
        f'Venta #{op_pk} eliminada. Se quitaron las comisiones asociadas.',
    )
    return redirect('inmobiliaria:operaciones_venta_lista')


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
    """
    partes_ars = [(v, Decimal(str(m or 0))) for v, m in (partes_ars or [])]
    honorarios_ars_total = sum((m for _v, m in partes_ars), Decimal('0')).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    cot = Decimal(str(op.cotizacion_dolar or 0))
    if cot > 0:
        total_usd = (honorarios_ars_total / cot).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
    else:
        total_usd = Decimal('0')

    if total_usd != op.honorarios_usd or honorarios_ars_total != op.honorarios_ars:
        op.honorarios_usd = total_usd
        op.honorarios_ars = honorarios_ars_total
        op.save(update_fields=['honorarios_usd', 'honorarios_ars', 'actualizado_en'])

    precio_ars = (op.precio_usd * cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cot else Decimal('0')
    dt = _fecha_operacion_aware(op.fecha_venta)
    estado_com = _estado_comision_venta(op.fecha_venta)
    dir_prop = (op.propiedad.direccion or '').strip() or f'#{op.propiedad_id}'
    creadas = []

    for vend, monto in partes_ars:
        if monto <= 0:
            continue
        usd_parte = (monto / cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cot else Decimal('0')
        pct_comision = Decimal('0')
        if precio_ars > 0:
            pct_comision = ((monto / precio_ars) * Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        creadas.append(
            ComisionVendedor.objects.create(
                vendedor=vend,
                monto_total_operacion=precio_ars,
                porcentaje_comision=pct_comision,
                monto_comision=monto,
                concepto_operacion=(
                    f'Venta propiedad #{op.propiedad_id} — {dir_prop} '
                    f'(U$S {op.precio_usd} @ {op.cotizacion_dolar})'
                )[:200],
                rol_comision=ROL_COMISION_VENTA,
                fecha_operacion=dt,
                estado=estado_com,
                observaciones=(
                    f'Operación venta #{op.pk}. Comisión cargada: ${monto} ARS '
                    f'(equiv. U$S {usd_parte} @ cotiz. {op.cotizacion_dolar}).'
                ),
            )
        )

    monto_f = Decimal(str(monto_fichaje_ars or 0)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP
    )
    fichado = op.fichado_por
    if fichado and monto_f > 0:
        usd_f = (monto_f / cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) if cot else Decimal('0')
        pct_f = Decimal('0')
        if honorarios_ars_total > 0:
            pct_f = ((monto_f / honorarios_ars_total) * Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        creadas.append(
            ComisionVendedor.objects.create(
                vendedor=fichado,
                monto_total_operacion=honorarios_ars_total or monto_f,
                porcentaje_comision=pct_f,
                monto_comision=monto_f,
                concepto_operacion=(
                    f'Fichaje venta #{op.propiedad_id} — {dir_prop}'
                )[:200],
                rol_comision=ROL_COMISION_FICHAJE,
                fecha_operacion=dt,
                estado=estado_com,
                observaciones=(
                    f'Operación venta #{op.pk}. Fichaje cargado: ${monto_f} ARS '
                    f'(equiv. U$S {usd_f}).'
                ),
            )
        )

    return creadas
