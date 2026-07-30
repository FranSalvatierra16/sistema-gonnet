"""Vistas del módulo Mis propiedades (cartera compartida por sucursal)."""
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from inmobiliaria.cartera_sucursal import (
    qs_cartera_sucursal,
    sincronizar_cartera_compartida_sucursal,
    usuario_titular_cartera,
)
from inmobiliaria.decimal_utils import format_monto_argentino, parse_decimal_monto
from inmobiliaria.models.caja import MovimientoCaja, TipoMovimientoCajaEnum
from inmobiliaria.models.cartera_usuario import CarteraPropiedadUsuario
from inmobiliaria.models.liquidacion import LiquidacionPropietario
from inmobiliaria.models.persona import Propietario
from inmobiliaria.models.propiedad import Propiedad
from inmobiliaria.neto_propietario_movimiento import (
    neto_propietario_movimiento,
    precios_por_propiedad_ids,
)

Q_SUCURSALES_COLON_CORRIENTES = (
    Q(sucursal__nombre__icontains='colon') | Q(sucursal__nombre__icontains='corrientes')
)


def _usuario_en_colon_o_corrientes(user):
    nombre_suc = (getattr(getattr(user, 'sucursal', None), 'nombre', None) or '').lower()
    return 'colon' in nombre_suc or 'corrientes' in nombre_suc


def _propietarios_busqueda_mis_propiedades(user):
    if _usuario_en_colon_o_corrientes(user):
        return Propietario.objects.filter(Q_SUCURSALES_COLON_CORRIENTES).select_related('sucursal')
    return Propietario.objects.filter(sucursal=user.sucursal).select_related('sucursal')


def _propietario_accesible_mis_propiedades(user, propietario_id):
    if not propietario_id:
        return None
    qs = Propietario.objects.filter(pk=propietario_id).select_related('sucursal')
    if _usuario_en_colon_o_corrientes(user):
        qs = qs.filter(Q_SUCURSALES_COLON_CORRIENTES)
    else:
        qs = qs.filter(sucursal=user.sucursal)
    return qs.first()


def _propiedades_en_mi_sucursal_para_propietario(propietario_sel, sucursal):
    """Propiedades del propietario en la sucursal del usuario (mismo DNI / ficha si es otra sucursal)."""
    if not propietario_sel:
        return Propiedad.objects.none()

    qs = Propiedad.objects.filter(sucursal=sucursal)
    q = Q()
    if propietario_sel.sucursal_id == sucursal.id:
        q |= Q(propietario_id=propietario_sel.id)

    dni = (propietario_sel.dni or '').strip()
    if dni:
        q |= Q(propietario__dni=dni)
    # Cruce entre sucursales o ficha sin DNI: misma persona por nombre.
    if propietario_sel.sucursal_id != sucursal.id or not dni:
        q |= Q(
            propietario__apellido__iexact=(propietario_sel.apellido or '').strip(),
            propietario__nombre__iexact=(propietario_sel.nombre or '').strip(),
        )

    if not q:
        return Propiedad.objects.none()
    return qs.filter(q).select_related('propietario', 'sucursal').distinct().order_by('direccion', 'id')


def _propiedades_de_propietario(propietario_id, sucursal):
    return (
        Propiedad.objects.filter(sucursal=sucursal, propietario_id=propietario_id)
        .select_related('propietario', 'sucursal')
        .order_by('direccion', 'id')
    )


def _factor_porcentaje(porcentaje):
    return Decimal(str(porcentaje or 0)) / Decimal('100')


def _resumen_movimientos_propiedad(propiedad_id, sucursal, porcentaje):
    """Ingresos (neto propietario IN) y gastos oficina (monto_a_oficina) prorrateados."""
    movs = list(
        MovimientoCaja.objects.filter(
            propiedad_id=propiedad_id,
            sucursal=sucursal,
        ).order_by('-fecha', '-id')
    )
    mov_ids = [m.id for m in movs]
    liq_por_mov = {}
    if mov_ids:
        for liq in LiquidacionPropietario.objects.filter(
            movimiento_caja_id__in=mov_ids
        ).exclude(estado='cancelada'):
            mid = liq.movimiento_caja_id
            if mid not in liq_por_mov:
                liq_por_mov[mid] = liq

    precios_map = precios_por_propiedad_ids([propiedad_id])
    factor = _factor_porcentaje(porcentaje)
    ingresos_bruto = Decimal('0')
    gastos_oficina = Decimal('0')
    ingresos_items = []
    gastos_items = []

    for m in movs:
        neto = neto_propietario_movimiento(m, liq_por_mov, precios_map)
        oficina = Decimal(str(getattr(m, 'monto_a_oficina', None) or 0))
        if m.tipo == TipoMovimientoCajaEnum.INGRESO and neto > 0:
            mi_parte = (neto * factor).quantize(Decimal('0.01'))
            ingresos_bruto += mi_parte
            ingresos_items.append({'movimiento': m, 'monto': mi_parte, 'neto_total': neto})
        if oficina > 0:
            mi_gasto = (oficina * factor).quantize(Decimal('0.01'))
            gastos_oficina += mi_gasto
            gastos_items.append({'movimiento': m, 'monto': mi_gasto, 'oficina_total': oficina})

    return {
        'ingresos_total': ingresos_bruto,
        'gastos_oficina_total': gastos_oficina,
        'ingresos_items': ingresos_items,
        'gastos_items': gastos_items,
    }


def _enriquecer_cartera_items(items, sucursal):
    """Agrega totales a cada ítem de cartera (sin listar todos los movimientos)."""
    if not items:
        return []
    prop_ids = [it.propiedad_id for it in items]
    movs = MovimientoCaja.objects.filter(
        propiedad_id__in=prop_ids,
        sucursal=sucursal,
    )
    ingresos_por_prop = {pid: Decimal('0') for pid in prop_ids}
    gastos_por_prop = {pid: Decimal('0') for pid in prop_ids}

    movs_list = list(movs)
    mov_ids = [m.id for m in movs_list if m.tipo == TipoMovimientoCajaEnum.INGRESO]
    liq_por_mov = {}
    if mov_ids:
        for liq in LiquidacionPropietario.objects.filter(
            movimiento_caja_id__in=mov_ids
        ).exclude(estado='cancelada'):
            mid = liq.movimiento_caja_id
            if mid not in liq_por_mov:
                liq_por_mov[mid] = liq
    precios_map = precios_por_propiedad_ids(prop_ids)

    for m in movs_list:
        pid = m.propiedad_id
        if m.tipo == TipoMovimientoCajaEnum.INGRESO:
            neto = neto_propietario_movimiento(m, liq_por_mov, precios_map)
            ingresos_por_prop[pid] = ingresos_por_prop.get(pid, Decimal('0')) + neto
        oficina = Decimal(str(getattr(m, 'monto_a_oficina', None) or 0))
        if oficina > 0:
            gastos_por_prop[pid] = gastos_por_prop.get(pid, Decimal('0')) + oficina

    resultado = []
    for it in items:
        factor = _factor_porcentaje(it.porcentaje)
        resultado.append({
            'item': it,
            'ingresos_mios': (ingresos_por_prop.get(it.propiedad_id, Decimal('0')) * factor).quantize(
                Decimal('0.01')
            ),
            'gastos_oficina_mios': (gastos_por_prop.get(it.propiedad_id, Decimal('0')) * factor).quantize(
                Decimal('0.01')
            ),
        })
    return resultado


@login_required
def mis_propiedades(request):
    sucursal = request.user.sucursal
    titular = sincronizar_cartera_compartida_sucursal(sucursal)
    cartera_qs = (
        qs_cartera_sucursal(sucursal, sincronizar=False)
        .select_related('propiedad', 'propiedad__propietario', 'propietario')
        .order_by('-fecha_alta')
    )
    cartera_items = _enriquecer_cartera_items(list(cartera_qs), sucursal)

    totales = {
        'ingresos': sum(r['ingresos_mios'] for r in cartera_items),
        'gastos_oficina': sum(r['gastos_oficina_mios'] for r in cartera_items),
    }

    detalle_cartera_id = request.GET.get('ver')
    detalle = None
    if detalle_cartera_id and titular:
        item = get_object_or_404(
            CarteraPropiedadUsuario,
            pk=detalle_cartera_id,
            usuario=titular,
            propiedad__sucursal=sucursal,
        )
        resumen = _resumen_movimientos_propiedad(item.propiedad_id, sucursal, item.porcentaje)
        detalle = {'item': item, **resumen}

    propietario_id = request.GET.get('propietario_id', '').strip()
    propietario = None
    propiedades_propietario = []
    ids_en_cartera = set(cartera_qs.values_list('propiedad_id', flat=True))
    if propietario_id.isdigit():
        propietario = _propietario_accesible_mis_propiedades(request.user, int(propietario_id))
        if propietario:
            for p in _propiedades_en_mi_sucursal_para_propietario(propietario, sucursal):
                propiedades_propietario.append({
                    'propiedad': p,
                    'ya_en_cartera': p.id in ids_en_cartera,
                })

    return render(
        request,
        'inmobiliaria/mis_propiedades/lista.html',
        {
            'cartera_items': cartera_items,
            'totales': totales,
            'detalle': detalle,
            'propietario': propietario,
            'propiedades_propietario': propiedades_propietario,
            'propietario_id': propietario_id,
            'puede_buscar_ambas_sucursales': _usuario_en_colon_o_corrientes(request.user),
            'sucursal_actual': sucursal,
            'cartera_compartida': True,
            'cartera_titular': titular,
        },
    )


@login_required
@require_GET
def mis_propiedades_buscar_propietario(request):
    term = (request.GET.get('q') or '').strip()
    if not term:
        return JsonResponse({'results': []})
    from inmobiliaria.busqueda_persona import ordenar_queryset_persona_por_termino, q_busqueda_persona
    qs = ordenar_queryset_persona_por_termino(
        _propietarios_busqueda_mis_propiedades(request.user).filter(q_busqueda_persona(term)),
        term,
    )[:15]
    results = [
        {
            'id': p.id,
            'text': f'{p.apellido}, {p.nombre} (DNI {p.dni or "—"}) — {p.sucursal.nombre}',
        }
        for p in qs
    ]
    return JsonResponse({'results': results})


@login_required
@require_POST
def mis_propiedades_agregar(request):
    sucursal = request.user.sucursal
    titular = sincronizar_cartera_compartida_sucursal(sucursal)
    if not titular:
        messages.error(request, 'No se pudo determinar el titular de la cartera de la sucursal.')
        return redirect('inmobiliaria:mis_propiedades')

    propiedad_ids = request.POST.getlist('propiedad_ids')
    propietario_id = (request.POST.get('propietario_id') or '').strip()
    try:
        porcentaje = parse_decimal_monto(request.POST.get('porcentaje', '100') or '100')
    except Exception:
        messages.error(request, 'El porcentaje ingresado no es válido.')
        return redirect('inmobiliaria:mis_propiedades')

    if porcentaje <= 0 or porcentaje > 100:
        messages.error(request, 'El porcentaje debe estar entre 0,01 y 100.')
        return redirect('inmobiliaria:mis_propiedades')

    propietario = None
    if propietario_id.isdigit():
        propietario = _propietario_accesible_mis_propiedades(request.user, int(propietario_id))

    ids_validos = []
    for raw in propiedad_ids:
        pid = str(raw).strip()
        if pid:
            ids_validos.append(pid)

    if not ids_validos:
        messages.warning(request, 'No seleccionaste ninguna propiedad.')
        return redirect('inmobiliaria:mis_propiedades')

    propiedades = Propiedad.objects.filter(id__in=ids_validos, sucursal=sucursal)
    agregadas = 0
    actualizadas = 0
    for prop in propiedades:
        obj, created = CarteraPropiedadUsuario.objects.update_or_create(
            usuario=titular,
            propiedad=prop,
            defaults={
                'porcentaje': porcentaje,
                'propietario': prop.propietario,
            },
        )
        if created:
            agregadas += 1
        else:
            actualizadas += 1

    if agregadas:
        messages.success(
            request,
            f'Se agregaron {agregadas} propiedad(es) a la cartera de la sucursal '
            f'con {format_monto_argentino(porcentaje, 2)}% de participación.',
        )
    if actualizadas:
        messages.info(request, f'Se actualizó el porcentaje de {actualizadas} propiedad(es) ya existentes.')

    url = reverse('inmobiliaria:mis_propiedades')
    if propietario:
        url = f'{url}?propietario_id={propietario.id}'
    return redirect(url)


@login_required
@require_POST
def mis_propiedades_quitar(request, pk):
    sucursal = request.user.sucursal
    titular = usuario_titular_cartera(sucursal)
    item = get_object_or_404(
        CarteraPropiedadUsuario,
        pk=pk,
        usuario=titular,
        propiedad__sucursal=sucursal,
    )
    prop_id = item.propiedad_id
    item.delete()
    messages.success(request, f'Propiedad #{prop_id} quitada de la cartera de la sucursal.')
    return redirect('inmobiliaria:mis_propiedades')


@login_required
@require_POST
def mis_propiedades_editar_porcentaje(request, pk):
    sucursal = request.user.sucursal
    titular = usuario_titular_cartera(sucursal)
    item = get_object_or_404(
        CarteraPropiedadUsuario,
        pk=pk,
        usuario=titular,
        propiedad__sucursal=sucursal,
    )
    try:
        porcentaje = parse_decimal_monto(request.POST.get('porcentaje', '') or '0')
    except Exception:
        messages.error(request, 'Porcentaje inválido.')
        return redirect('inmobiliaria:mis_propiedades')

    if porcentaje <= 0 or porcentaje > 100:
        messages.error(request, 'El porcentaje debe estar entre 0,01 y 100.')
        return redirect('inmobiliaria:mis_propiedades')

    item.porcentaje = porcentaje
    item.save(update_fields=['porcentaje'])
    messages.success(
        request,
        f'Porcentaje actualizado a {format_monto_argentino(porcentaje, 2)}% para la propiedad #{item.propiedad_id}.',
    )
    return redirect('inmobiliaria:mis_propiedades')
