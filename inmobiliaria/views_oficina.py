"""Módulo Oficina: gastos, categorías y acceso a honorarios, vales, comisiones y cartera."""
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from inmobiliaria.models import (
    Caja,
    CarteraPropiedadUsuario,
    CategoriaGastoOficina,
    ComisionVendedor,
    GastoOficina,
    LiquidacionPropietario,
    ValeVendedor,
)
from inmobiliaria.models.persona import usuario_es_nivel_administracion
from inmobiliaria.oficina_gastos import (
    asegurar_categoria_vales,
    asegurar_categorias_base,
    asegurar_estructura_cierre_oficina,
    propagar_categoria_oficina_a_espejos,
    reubicar_raices_personalizadas_al_final,
    siguiente_orden_categoria,
)
from inmobiliaria.oficina_resumen import construir_resumen_cierre


def _parse_fecha(s):
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _puede_oficina(user):
    return usuario_es_nivel_administracion(user)


def _arbol_categorias(sucursal, solo_activas=True):
    raices = (
        CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent__isnull=True)
        .prefetch_related('subcategorias__vendedor')
        .order_by('orden', 'nombre')
    )
    arbol = []
    for raiz in raices:
        if solo_activas and not raiz.activa:
            continue
        hijos = list(raiz.subcategorias.order_by('orden', 'nombre'))
        if solo_activas:
            hijos = [h for h in hijos if h.activa]
        arbol.append({'categoria': raiz, 'hijos': hijos})
    return arbol


def _arbol_categorias_admin(sucursal):
    """Árbol completo (activas e inactivas) con conteo de gastos."""
    raices = (
        CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent__isnull=True)
        .annotate(num_gastos=Count('gastos'))
        .prefetch_related('subcategorias__vendedor')
        .order_by('orden', 'nombre')
    )
    arbol = []
    for raiz in raices:
        hijos = list(
            raiz.subcategorias.annotate(num_gastos=Count('gastos'))
            .select_related('vendedor')
            .order_by('orden', 'nombre')
        )
        arbol.append({'categoria': raiz, 'hijos': hijos})
    return arbol


def _categoria_bloqueada_por_vendedor(cat):
    return bool(getattr(cat, 'vendedor_id', None))


def _totales_gastos_por_raiz(qs_gastos):
    totales = defaultdict(lambda: Decimal('0'))
    for g in qs_gastos.select_related('categoria', 'categoria__parent'):
        raiz = g.categoria_raiz
        nombre = raiz.nombre if raiz else 'Sin categoría'
        totales[nombre] += g.monto or Decimal('0')
    return dict(totales)


@login_required
def oficina_dashboard(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)
    asegurar_estructura_cierre_oficina(sucursal)

    today = timezone.localdate()
    mes_ini = today.replace(day=1)

    gastos_mes = GastoOficina.objects.filter(
        sucursal=sucursal,
        fecha__gte=mes_ini,
        fecha__lte=today,
    )
    total_gastos_mes = gastos_mes.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    totales_por_categoria = _totales_gastos_por_raiz(gastos_mes)

    honorarios_mes = LiquidacionPropietario.objects.filter(
        sucursal=sucursal,
    ).exclude(estado='cancelada')
    # Aproximación ingresos mes: liquidaciones creadas en el mes
    honorarios_mes = honorarios_mes.filter(
        fecha_creacion__date__gte=mes_ini,
        fecha_creacion__date__lte=today,
    )
    ingresos_mes = Decimal('0')
    for liq in honorarios_mes.only(
        'monto_inmobiliaria', 'monto_cochera', 'monto_fondo_mantenimiento'
    ):
        ingresos_mes += (
            Decimal(str(liq.monto_inmobiliaria or 0))
            + Decimal(str(liq.monto_cochera or 0))
            + Decimal(str(liq.monto_fondo_mantenimiento or 0))
        )

    comisiones_pendientes = ComisionVendedor.objects.filter(
        vendedor__sucursal=sucursal,
        estado='pendiente',
    ).count()
    vales_abiertos = ValeVendedor.objects.filter(
        vendedor__sucursal=sucursal,
    ).count()
    propiedades_cartera = CarteraPropiedadUsuario.objects.filter(
        propiedad__sucursal=sucursal,
    ).values('propiedad').distinct().count()

    from inmobiliaria.models import Propiedad

    propiedades_oficina_count = Propiedad.objects.filter(
        sucursal=sucursal, es_propiedad_oficina=True
    ).count()

    return render(
        request,
        'inmobiliaria/oficina/dashboard.html',
        {
            'total_gastos_mes': total_gastos_mes,
            'ingresos_honorarios_mes': ingresos_mes,
            'totales_por_categoria': sorted(totales_por_categoria.items()),
            'comisiones_pendientes': comisiones_pendientes,
            'vales_count': vales_abiertos,
            'propiedades_cartera': propiedades_cartera,
            'propiedades_oficina_count': propiedades_oficina_count,
            'mes_label': mes_ini.strftime('%B %Y'),
        },
    )


@login_required
def oficina_gastos(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)
    asegurar_estructura_cierre_oficina(sucursal)

    fecha_desde_s = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta_s = (request.GET.get('fecha_hasta') or '').strip()
    categoria_id = (request.GET.get('categoria') or '').strip()
    q = (request.GET.get('q') or '').strip()

    today = timezone.localdate()
    if not fecha_desde_s and not fecha_hasta_s:
        fecha_desde_s = today.replace(day=1).isoformat()
        fecha_hasta_s = today.isoformat()

    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    qs = GastoOficina.objects.filter(sucursal=sucursal).select_related(
        'categoria', 'categoria__parent', 'usuario_creacion', 'vendedor', 'movimiento_caja'
    )
    if dr_desde:
        qs = qs.filter(fecha__gte=dr_desde)
    if dr_hasta:
        qs = qs.filter(fecha__lte=dr_hasta)
    if categoria_id.isdigit():
        cat = CategoriaGastoOficina.objects.filter(
            sucursal=sucursal, id=int(categoria_id)
        ).first()
        if cat:
            hijos_ids = list(
                CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent=cat).values_list(
                    'id', flat=True
                )
            )
            ids = [cat.id] + hijos_ids
            qs = qs.filter(categoria_id__in=ids)
    if q:
        qs = qs.filter(descripcion__icontains=q)

    total = qs.aggregate(t=Sum('monto'))['t'] or Decimal('0')
    gastos = list(qs.order_by('-fecha', '-id')[:500])
    totales_por_categoria = _totales_gastos_por_raiz(qs)

    raices_filtro = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal, parent__isnull=True, activa=True
    ).order_by('orden', 'nombre')

    caja_abierta = (
        Caja.objects.filter(sucursal=sucursal, estado='abierta')
        .order_by('-fecha_apertura')
        .first()
    )

    return render(
        request,
        'inmobiliaria/oficina/gastos_lista.html',
        {
            'gastos': gastos,
            'total': total,
            'totales_por_categoria': sorted(totales_por_categoria.items()),
            'fecha_desde': fecha_desde_s,
            'fecha_hasta': fecha_hasta_s,
            'categoria_filtro': categoria_id,
            'q': q,
            'raices_filtro': raices_filtro,
            'caja_abierta': caja_abierta,
        },
    )


@login_required
@require_POST
def oficina_gasto_crear(request):
    """Los gastos se cargan desde Nuevo movimiento de caja, no desde este panel."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    messages.info(
        request,
        'Los gastos de oficina se registran desde Caja → Nuevo movimiento, '
        'marcando «Gasto de oficina».',
    )
    return redirect('inmobiliaria:oficina_gastos')


@login_required
@require_POST
def oficina_gasto_eliminar(request, gasto_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    gasto = get_object_or_404(
        GastoOficina.objects.select_related('movimiento_caja'),
        id=gasto_id,
        sucursal=request.user.sucursal,
    )
    if gasto.movimiento_caja_id:
        messages.error(
            request,
            f'Este gasto está vinculado al movimiento de caja #{gasto.movimiento_caja_id}. '
            'Eliminá o anulá el movimiento desde la caja.',
        )
        return redirect('inmobiliaria:oficina_gastos')
    gasto.delete()
    messages.success(request, 'Gasto eliminado.')
    return redirect('inmobiliaria:oficina_gastos')


@login_required
def oficina_categorias(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_categorias_base(sucursal)
    reubicar_raices_personalizadas_al_final(sucursal)

    return render(
        request,
        'inmobiliaria/oficina/categorias.html',
        {
            'arbol': _arbol_categorias_admin(sucursal),
        },
    )


@login_required
@require_POST
def oficina_categoria_crear(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    nombre = (request.POST.get('nombre') or '').strip()
    parent_id = (request.POST.get('parent_id') or '').strip()

    if not nombre:
        messages.error(request, 'El nombre es obligatorio.')
        return redirect('inmobiliaria:oficina_categorias')

    parent = None
    if parent_id.isdigit():
        parent = get_object_or_404(
            CategoriaGastoOficina,
            id=int(parent_id),
            sucursal=sucursal,
            parent__isnull=True,
        )

    if CategoriaGastoOficina.objects.filter(
        sucursal=sucursal, parent=parent, nombre__iexact=nombre
    ).exists():
        messages.error(request, 'Ya existe una categoría con ese nombre.')
        return redirect('inmobiliaria:oficina_categorias')

    cat = CategoriaGastoOficina.objects.create(
        sucursal=sucursal,
        parent=parent,
        nombre=nombre,
        orden=siguiente_orden_categoria(sucursal, parent),
        activa=True,
    )
    if parent and not parent.activa:
        parent.activa = True
        parent.save(update_fields=['activa'])
        propagar_categoria_oficina_a_espejos(parent, accion='toggle', cascade_hijos=False)
    propagar_categoria_oficina_a_espejos(cat, accion='upsert')
    messages.success(
        request,
        'Subcategoría creada.' if parent else 'Categoría creada.',
    )
    return redirect('inmobiliaria:oficina_categorias')


@login_required
@require_POST
def oficina_categoria_toggle(request, categoria_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    cat = get_object_or_404(
        CategoriaGastoOficina.objects.select_related('parent'),
        id=categoria_id,
        sucursal=request.user.sucursal,
    )
    cat.activa = not cat.activa
    cat.save(update_fields=['activa'])
    cascade = cat.parent_id is None and not (request.POST.get('solo_esta') == '1')
    if cascade:
        CategoriaGastoOficina.objects.filter(sucursal=cat.sucursal, parent=cat).update(
            activa=cat.activa
        )
        messages.success(
            request,
            f'Categoría «{cat.nombre}» y sus subcategorías '
            f'{"activadas" if cat.activa else "desactivadas"}.',
        )
    else:
        messages.success(
            request,
            f'{"Activada" if cat.activa else "Desactivada"}: {cat.nombre_ruta()}.',
        )
    propagar_categoria_oficina_a_espejos(cat, accion='toggle', cascade_hijos=cascade)
    return redirect('inmobiliaria:oficina_categorias')


@login_required
@require_POST
def oficina_categoria_editar(request, categoria_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    cat = get_object_or_404(
        CategoriaGastoOficina.objects.select_related('parent'),
        id=categoria_id,
        sucursal=request.user.sucursal,
    )
    if _categoria_bloqueada_por_vendedor(cat):
        messages.error(
            request,
            'Las subcategorías vinculadas a un vendedor se sincronizan solas; '
            'no se pueden renombrar desde acá.',
        )
        return redirect('inmobiliaria:oficina_categorias')

    nombre = (request.POST.get('nombre') or '').strip()
    if not nombre:
        messages.error(request, 'El nombre es obligatorio.')
        return redirect('inmobiliaria:oficina_categorias')

    if CategoriaGastoOficina.objects.filter(
        sucursal=cat.sucursal,
        parent=cat.parent,
        nombre__iexact=nombre,
    ).exclude(pk=cat.pk).exists():
        messages.error(request, 'Ya existe otra categoría con ese nombre.')
        return redirect('inmobiliaria:oficina_categorias')

    nombre_anterior = cat.nombre
    cat.nombre = nombre
    cat.save(update_fields=['nombre'])
    propagar_categoria_oficina_a_espejos(
        cat, accion='rename', nombre_anterior=nombre_anterior
    )
    messages.success(request, f'Nombre actualizado: {cat.nombre_ruta()}.')
    return redirect('inmobiliaria:oficina_categorias')


@login_required
@require_POST
def oficina_categoria_eliminar(request, categoria_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    cat = get_object_or_404(
        CategoriaGastoOficina.objects.select_related('parent'),
        id=categoria_id,
        sucursal=request.user.sucursal,
    )
    if _categoria_bloqueada_por_vendedor(cat):
        messages.error(
            request,
            'No se puede eliminar una subcategoría de vendedor; desactivarla si no la usás.',
        )
        return redirect('inmobiliaria:oficina_categorias')

    nombre = cat.nombre_ruta()
    num_gastos = cat.gastos.count()
    if cat.parent_id is None:
        num_gastos += GastoOficina.objects.filter(categoria__parent=cat).count()
    if num_gastos:
        messages.error(
            request,
            f'No se puede eliminar «{nombre}»: tiene {num_gastos} gasto(s) registrado(s). '
            'Desactivarla en su lugar.',
        )
        return redirect('inmobiliaria:oficina_categorias')

    # Propagar antes de borrar el local (necesita nombre/parent).
    propagar_categoria_oficina_a_espejos(cat, accion='delete')
    try:
        cat.delete()
    except ProtectedError:
        messages.error(
            request,
            f'No se puede eliminar «{nombre}» porque hay gastos vinculados.',
        )
        return redirect('inmobiliaria:oficina_categorias')

    messages.success(request, f'Eliminada: {nombre}.')
    return redirect('inmobiliaria:oficina_categorias')


@login_required
def oficina_resumen_cierre(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    asegurar_estructura_cierre_oficina(sucursal)

    today = timezone.localdate()
    anio_s = (request.GET.get('anio') or '').strip()
    mes_s = (request.GET.get('mes') or '').strip()
    try:
        anio = int(anio_s) if anio_s else today.year
        mes = int(mes_s) if mes_s else today.month
        if mes < 1 or mes > 12:
            raise ValueError
    except (TypeError, ValueError):
        anio, mes = today.year, today.month

    resumen = construir_resumen_cierre(sucursal, anio, mes)

    anios_opts = list(range(today.year - 2, today.year + 2))
    meses_opts = list(enumerate(
        ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
        start=1,
    ))

    return render(
        request,
        'inmobiliaria/oficina/resumen_cierre.html',
        {
            **resumen,
            'anios_opts': anios_opts,
            'meses_opts': meses_opts,
            'anio_sel': anio,
            'mes_sel': mes,
        },
    )


def _qs_propiedades_oficina(sucursal):
    from inmobiliaria.models import Propiedad

    return (
        Propiedad.objects.filter(sucursal=sucursal, es_propiedad_oficina=True)
        .select_related('propietario')
        .order_by('direccion', 'piso', 'departamento', 'id')
    )


def _descripcion_movimiento_libro(mov):
    """Texto legible para la columna Descripción del libro."""
    try:
        txt = (mov.concepto_sin_pipe_conceptos() or '').strip()
    except Exception:
        txt = (getattr(mov, 'concepto', None) or '').strip()
        if '|CONCEPTOS:' in txt:
            txt = txt.split('|CONCEPTOS:', 1)[0].strip()
    return txt or f'Movimiento #{mov.id}'


def _fila_libro_desde_movimiento(mov):
    """
    Mapea un MovimientoCaja a las columnas del libro:
    gastos_ars, alquileres_ars, gastos_usd, ingreso_usd, tipo_cambio.
    """
    from inmobiliaria.models.caja import TipoMovimientoCajaEnum

    ars = Decimal(str(getattr(mov, 'monto_total', 0) or 0))
    usd = Decimal(str(getattr(mov, 'monto_dolares', 0) or 0))
    cotiz = getattr(mov, 'cotizacion_dolar', None)
    if cotiz is not None:
        cotiz = Decimal(str(cotiz))
        if cotiz <= 0:
            cotiz = None

    es_egreso = (getattr(mov, 'tipo', None) or '').strip().upper() == TipoMovimientoCajaEnum.EGRESO

    gastos_ars = Decimal('0')
    alquileres_ars = Decimal('0')
    gastos_usd = Decimal('0')
    ingreso_usd = Decimal('0')

    if es_egreso:
        gastos_ars = ars
        if usd > 0:
            gastos_usd = usd
        elif ars > 0 and cotiz:
            gastos_usd = (ars / cotiz).quantize(Decimal('0.01'))
    else:
        alquileres_ars = ars
        if usd > 0:
            ingreso_usd = usd
        elif ars > 0 and cotiz:
            ingreso_usd = (ars / cotiz).quantize(Decimal('0.01'))

    return {
        'fecha': mov.fecha,
        'descripcion': _descripcion_movimiento_libro(mov),
        'gastos_ars': gastos_ars,
        'alquileres_ars': alquileres_ars,
        'gastos_usd': gastos_usd,
        'ingreso_usd': ingreso_usd,
        'tipo_cambio': cotiz,
        'movimiento_id': mov.id,
        'tipo': 'EG' if es_egreso else 'IN',
    }


@login_required
def oficina_propiedades_lista(request):
    """Listado de departamentos marcados como propiedad oficina."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    propiedades = list(_qs_propiedades_oficina(sucursal))
    return render(
        request,
        'inmobiliaria/oficina/propiedades_lista.html',
        {
            'propiedades': propiedades,
            'total': len(propiedades),
        },
    )


@login_required
def oficina_propiedad_libro(request, propiedad_id):
    """Libro automático (estilo planilla) de movimientos de caja de un depto oficina."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    from inmobiliaria.models import MovimientoCaja, Propiedad

    sucursal = request.user.sucursal
    propiedad = get_object_or_404(
        Propiedad.objects.select_related('propietario'),
        pk=propiedad_id,
        sucursal=sucursal,
        es_propiedad_oficina=True,
    )

    fecha_desde_s = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta_s = (request.GET.get('fecha_hasta') or '').strip()
    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    mov_qs = (
        MovimientoCaja.objects.filter(
            sucursal=sucursal,
            propiedad=propiedad,
            fecha_eliminacion__isnull=True,
        )
        .order_by('fecha', 'id')
    )
    if dr_desde:
        mov_qs = mov_qs.filter(fecha__date__gte=dr_desde)
    if dr_hasta:
        mov_qs = mov_qs.filter(fecha__date__lte=dr_hasta)

    filas = [_fila_libro_desde_movimiento(m) for m in mov_qs[:2000]]

    totales = {
        'gastos_ars': sum((f['gastos_ars'] for f in filas), Decimal('0')),
        'alquileres_ars': sum((f['alquileres_ars'] for f in filas), Decimal('0')),
        'gastos_usd': sum((f['gastos_usd'] for f in filas), Decimal('0')),
        'ingreso_usd': sum((f['ingreso_usd'] for f in filas), Decimal('0')),
    }
    totales['balance_ars'] = totales['alquileres_ars'] - totales['gastos_ars']
    totales['balance_usd'] = totales['ingreso_usd'] - totales['gastos_usd']

    otras = list(_qs_propiedades_oficina(sucursal))

    return render(
        request,
        'inmobiliaria/oficina/propiedad_libro.html',
        {
            'propiedad': propiedad,
            'filas': filas,
            'totales': totales,
            'otras_propiedades': otras,
            'fecha_desde': fecha_desde_s,
            'fecha_hasta': fecha_hasta_s,
        },
    )
