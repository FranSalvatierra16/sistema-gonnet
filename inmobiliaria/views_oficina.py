"""Módulo Oficina: gastos, categorías y acceso a honorarios, vales, comisiones y cartera."""
import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)

from inmobiliaria.cartera_sucursal import (
    qs_cartera_sucursal,
    sincronizar_cartera_compartida_sucursal,
    usuario_titular_cartera,
)
from inmobiliaria.models import (
    Caja,
    CarteraPropiedadUsuario,
    CategoriaGastoOficina,
    ComisionVendedor,
    CostosCompraLibroPropiedad,
    CotizacionLibroOperacion,
    FilaManualLibroPropiedad,
    GastoOficina,
    InicioCajaLibroPropiedad,
    LiquidacionPropietario,
    ValeVendedor,
)
from inmobiliaria.models.persona import usuario_es_nivel_administracion
from inmobiliaria.oficina_gastos import (
    asegurar_categoria_vales,
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


def _ids_operaciones_contratos_propiedad(propiedad, sucursal):
    """IDs de reservas (operaciones) y contratos de la propiedad."""
    from inmobiliaria.models import ContratoAlquiler, Reserva

    reserva_ids = list(
        Reserva.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
            eliminada=False,
        ).values_list('id', flat=True)[:800]
    )
    contrato_ids = list(
        ContratoAlquiler.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
        ).values_list('id', flat=True)[:400]
    )
    return [int(x) for x in reserva_ids], [int(x) for x in contrato_ids]


def _movimiento_refiere_operacion_o_contrato(concepto, reserva_ids, contrato_ids):
    """True si el texto del concepto menciona Operación N o Contrato #N de esta propiedad."""
    import re

    txt = concepto or ''
    if not txt:
        return False
    res_set = reserva_ids if isinstance(reserva_ids, (set, frozenset)) else set(reserva_ids or [])
    ctr_set = contrato_ids if isinstance(contrato_ids, (set, frozenset)) else set(contrato_ids or [])
    if res_set:
        for m in re.finditer(r'Operaci[oó]n\s*#?\s*(\d+)\b', txt, re.IGNORECASE):
            if int(m.group(1)) in res_set:
                return True
    if ctr_set:
        for m in re.finditer(r'Contrato\s*#\s*(\d+)\b', txt, re.IGNORECASE):
            if int(m.group(1)) in ctr_set:
                return True
    return False


def _qs_movimientos_libro_propiedad(sucursal, propiedad, dr_desde=None, dr_hasta=None):
    """
    Movimientos del libro: los de la propiedad en caja + ingresos/egresos
    de operaciones y contratos de ese depto (aunque falte el FK propiedad).
    """
    from django.db.models import Q

    from inmobiliaria.models import MovimientoCaja

    reserva_ids, contrato_ids = _ids_operaciones_contratos_propiedad(propiedad, sucursal)
    reserva_set = set(reserva_ids)
    contrato_set = set(contrato_ids)

    base = MovimientoCaja.objects.filter(
        sucursal=sucursal,
        fecha_eliminacion__isnull=True,
    )
    if dr_desde:
        base = base.filter(fecha__date__gte=dr_desde)
    if dr_hasta:
        base = base.filter(fecha__date__lte=dr_hasta)

    # 1) Directos por FK propiedad
    por_prop = list(base.filter(propiedad=propiedad).order_by('fecha', 'id')[:2000])
    seen = {m.id for m in por_prop}

    # 2) Candidatos por texto (una query amplia) y filtro exacto en Python
    extras = []
    if reserva_set or contrato_set:
        q_ref = Q()
        if reserva_set:
            q_ref |= Q(concepto__icontains='Operación') | Q(concepto__icontains='Operacion')
        if contrato_set:
            q_ref |= Q(concepto__icontains='Contrato #') | Q(concepto__icontains='Contrato#')
        candidatos = (
            base.filter(q_ref)
            .exclude(id__in=seen)
            .order_by('fecha', 'id')[:3000]
        )
        for mov in candidatos:
            if _movimiento_refiere_operacion_o_contrato(
                getattr(mov, 'concepto', None) or '',
                reserva_ids,
                contrato_ids,
            ):
                extras.append(mov)
                seen.add(mov.id)

    todos = por_prop + extras
    todos.sort(key=lambda m: (m.fecha or timezone.now(), m.id or 0))
    return todos, reserva_ids, contrato_ids


def _nombre_cliente_corto(persona):
    if not persona:
        return ''
    ap = (getattr(persona, 'apellido', None) or '').strip()
    nom = (getattr(persona, 'nombre', None) or '').strip()
    if ap and nom:
        return f'{ap}, {nom}'
    return ap or nom or ''


def _monto_propietario_reserva_libro(reserva, liquidacion=None):
    """
    Monto que va al propietario (depto) para el libro:
    liquidación > override de carátula > reparto por día.
    """
    if liquidacion is not None and getattr(liquidacion, 'estado', '') != 'cancelada':
        mp = Decimal(str(getattr(liquidacion, 'monto_propietario', None) or 0))
        if mp > 0:
            return mp.quantize(Decimal('0.01'))
        ma = Decimal(str(getattr(liquidacion, 'monto_a_pagar', None) or 0))
        if ma > 0:
            return ma.quantize(Decimal('0.01'))

    if getattr(reserva, 'liq_monto_propietario', None) is not None:
        return Decimal(str(reserva.liq_monto_propietario)).quantize(Decimal('0.01'))

    from inmobiliaria.neto_propietario_movimiento import reparto_liquidacion_reserva_por_dia

    total, prop, inm, _hay = reparto_liquidacion_reserva_por_dia(reserva)
    _t, prop, _i, _c, _f = reserva.montos_liquidacion_efectivos(total, prop, inm)
    return Decimal(str(prop or 0)).quantize(Decimal('0.01'))


def _liquidaciones_por_reserva(reserva_ids):
    """reserva_id -> LiquidacionPropietario más reciente no cancelada."""
    from inmobiliaria.models import LiquidacionPropietario

    if not reserva_ids:
        return {}
    out = {}
    for liq in (
        LiquidacionPropietario.objects.filter(reserva_id__in=reserva_ids)
        .exclude(estado='cancelada')
        .order_by('-id')
        .only(
            'id',
            'reserva_id',
            'estado',
            'monto_propietario',
            'monto_a_pagar',
            'movimiento_caja_id',
        )
    ):
        rid = liq.reserva_id
        if rid and rid not in out:
            out[rid] = liq
    return out


def _filas_operaciones_faltantes_libro(
    propiedad,
    sucursal,
    reserva_ids,
    movimientos,
    dr_desde=None,
    dr_hasta=None,
    liq_por_reserva=None,
    cotiz_por_reserva=None,
):
    """
    Operaciones (reservas con cobro) de la propiedad que no aparecen en caja:
    se agregan como filas de alquiler con el monto al propietario (no el total).
    """
    import re

    from inmobiliaria.caja_devolucion_deposito import queryset_reservas_con_operacion
    from inmobiliaria.models import Reserva

    if not reserva_ids:
        return []

    liq_por_reserva = liq_por_reserva or {}
    cotiz_por_reserva = cotiz_por_reserva or {}

    cubiertas = set()
    for mov in movimientos:
        txt = getattr(mov, 'concepto', None) or ''
        for rid in reserva_ids:
            if re.search(rf'Operaci[oó]n\s*#?\s*{rid}\b', txt, re.IGNORECASE):
                cubiertas.add(rid)

    qs = queryset_reservas_con_operacion(
        Reserva.objects.filter(
            id__in=reserva_ids,
            propiedad=propiedad,
            sucursal=sucursal,
            eliminada=False,
        ).select_related('cliente')
    )
    filas = []
    for r in qs:
        if r.id in cubiertas:
            continue
        fecha = getattr(r, 'fecha_creacion', None) or timezone.now()
        f_date = fecha.date() if hasattr(fecha, 'date') else fecha
        if dr_desde and f_date < dr_desde:
            continue
        if dr_hasta and f_date > dr_hasta:
            continue
        monto = _monto_propietario_reserva_libro(r, liq_por_reserva.get(r.id))
        if monto <= 0:
            continue
        cliente = _nombre_cliente_corto(r.cliente)
        desc = f'Operación {r.id}'
        if cliente:
            desc = f'{desc} — {cliente}'
        moneda = (getattr(r, 'moneda', None) or 'ARS').strip().upper()
        cotiz = cotiz_por_reserva.get(r.id)
        if cotiz is not None:
            cotiz = Decimal(str(cotiz))
            if cotiz <= 0:
                cotiz = None
        fila = {
            'fecha': fecha,
            'descripcion': desc,
            'gastos_ars': Decimal('0'),
            'alquileres_ars': Decimal('0'),
            'gastos_usd': Decimal('0'),
            'ingreso_usd': Decimal('0'),
            'tipo_cambio': cotiz,
            'movimiento_id': None,
            'tipo': 'IN',
            'sin_caja': True,
            'es_inicio_caja': False,
            'es_manual': False,
            'fila_manual_id': None,
            'es_operacion_libro': True,
            'reserva_id': r.id,
        }
        if moneda == 'USD':
            fila['ingreso_usd'] = monto
            if cotiz:
                fila['alquileres_ars'] = (monto * cotiz).quantize(Decimal('0.01'))
        else:
            fila['alquileres_ars'] = monto
            if cotiz:
                fila['ingreso_usd'] = (monto / cotiz).quantize(Decimal('0.01'))
        filas.append(fila)
    return filas


def _filas_contratos_faltantes_libro(
    propiedad,
    sucursal,
    contrato_ids,
    movimientos,
    dr_desde=None,
    dr_hasta=None,
):
    """
    Cobros de contrato (cuotas pagadas) sin movimiento visible en el libro:
    se listan como alquileres a partir de las cuotas.
    """
    import re
    from datetime import date as date_cls
    from datetime import time as time_cls

    from inmobiliaria.models import ContratoAlquiler

    if not contrato_ids:
        return []

    cubiertos = set()
    for mov in movimientos:
        txt = getattr(mov, 'concepto', None) or ''
        for cid in contrato_ids:
            if re.search(rf'Contrato\s*#\s*{cid}\b', txt, re.IGNORECASE):
                cubiertos.add(cid)

    faltan = [cid for cid in contrato_ids if cid not in cubiertos]
    if not faltan:
        return []

    contratos = (
        ContratoAlquiler.objects.filter(
            id__in=faltan,
            propiedad=propiedad,
            sucursal=sucursal,
        )
        .select_related('inquilino')
        .prefetch_related('cuotas')
    )
    filas = []
    for c in contratos:
        cliente = _nombre_cliente_corto(c.inquilino)
        moneda = (getattr(c, 'moneda', None) or 'ARS').strip().upper()
        for cuota in c.cuotas.all():
            estado = (getattr(cuota, 'estado', None) or '').lower()
            if estado not in ('pagada', 'pagada_con_mora'):
                continue
            fecha_raw = (
                getattr(cuota, 'fecha_pago', None)
                or getattr(cuota, 'fecha_vencimiento', None)
                or getattr(c, 'fecha_operacion', None)
            )
            if fecha_raw is None:
                continue
            if isinstance(fecha_raw, datetime):
                f_date = fecha_raw.date()
                f_dt = fecha_raw
            elif isinstance(fecha_raw, date_cls):
                f_date = fecha_raw
                f_dt = datetime.combine(f_date, time_cls.min)
                if timezone.is_naive(f_dt):
                    try:
                        f_dt = timezone.make_aware(f_dt)
                    except Exception:
                        pass
            else:
                continue
            if dr_desde and f_date < dr_desde:
                continue
            if dr_hasta and f_date > dr_hasta:
                continue
            monto = Decimal(
                str(
                    getattr(cuota, 'monto_total', None)
                    or getattr(cuota, 'monto', None)
                    or 0
                )
            )
            if monto <= 0:
                continue
            nro = getattr(cuota, 'numero_cuota', None) or ''
            desc = f'Contrato #{c.id}'
            if nro:
                desc = f'{desc} — Cuota {nro}'
            if cliente:
                desc = f'{desc} — {cliente}'
            fila = {
                'fecha': f_dt,
                'descripcion': desc,
                'gastos_ars': Decimal('0'),
                'alquileres_ars': Decimal('0'),
                'gastos_usd': Decimal('0'),
                'ingreso_usd': Decimal('0'),
                'tipo_cambio': None,
                'movimiento_id': None,
                'tipo': 'IN',
                'sin_caja': True,
                'es_inicio_caja': False,
                'es_manual': False,
                'fila_manual_id': None,
            }
            if moneda == 'USD':
                fila['ingreso_usd'] = monto
            else:
                fila['alquileres_ars'] = monto
            filas.append(fila)
    return filas


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


def _sync_categorias_oficina_seguro(sucursal):
    """Sincroniza categorías una sola vez; no tumba la pantalla si falla."""
    if not sucursal:
        return
    try:
        asegurar_estructura_cierre_oficina(sucursal)
    except Exception:
        logger.exception(
            'oficina: falló sync de categorías (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )


@login_required
def oficina_dashboard(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')

    _sync_categorias_oficina_seguro(sucursal)

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
    propiedades_cartera = qs_cartera_sucursal(sucursal).count()

    propiedades_oficina_count = propiedades_cartera

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
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')
    _sync_categorias_oficina_seguro(sucursal)

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
        'categoria', 'categoria__parent', 'usuario_creacion', 'vendedor',
        'movimiento_caja', 'gasto_relacionado',
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
        GastoOficina.objects.select_related('movimiento_caja', 'gasto_relacionado'),
        id=gasto_id,
        sucursal=request.user.sucursal,
    )
    # Si el par (u este) tiene movimiento de caja, hay que anular desde caja.
    mov_id = gasto.movimiento_caja_id
    if not mov_id and gasto.gasto_relacionado_id:
        mov_id = gasto.gasto_relacionado.movimiento_caja_id
    if not mov_id:
        pareja = GastoOficina.objects.filter(gasto_relacionado_id=gasto.id).first()
        if pareja and pareja.movimiento_caja_id:
            mov_id = pareja.movimiento_caja_id
    if mov_id:
        messages.error(
            request,
            f'Este gasto está vinculado al movimiento de caja #{mov_id}. '
            'Eliminá o anulá el movimiento desde la caja (se borra el reparto en ambas sucursales).',
        )
        return redirect('inmobiliaria:oficina_gastos')
    ids = {gasto.id}
    if gasto.gasto_relacionado_id:
        ids.add(gasto.gasto_relacionado_id)
    ids.update(
        GastoOficina.objects.filter(gasto_relacionado_id=gasto.id).values_list('id', flat=True)
    )
    GastoOficina.objects.filter(id__in=ids).delete()
    messages.success(request, 'Gasto eliminado.')
    return redirect('inmobiliaria:oficina_gastos')


@login_required
def oficina_categorias(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')
    _sync_categorias_oficina_seguro(sucursal)
    try:
        reubicar_raices_personalizadas_al_final(sucursal)
    except Exception:
        logger.exception(
            'oficina_categorias: falló reubicar raíces (sucursal_id=%s)',
            getattr(sucursal, 'pk', None),
        )

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
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')
    _sync_categorias_oficina_seguro(sucursal)

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


def _qs_propiedades_oficina(sucursal, usuario=None):
    """
    Propiedades del libro de oficina = cartera compartida de la sucursal
    (Mis propiedades). El parámetro usuario se ignora (compatibilidad).
    """
    from inmobiliaria.models import Propiedad

    if not sucursal:
        return Propiedad.objects.none()

    ids = (
        qs_cartera_sucursal(sucursal)
        .values_list('propiedad_id', flat=True)
        .distinct()
    )
    return (
        Propiedad.objects.filter(id__in=ids, sucursal=sucursal)
        .select_related('propietario')
        .order_by('direccion', 'piso', 'departamento', 'id')
    )


def _parse_items_concepto_json(raw):
    """Extrae lista de conceptos desde JSON (array o {conceptos: [...]})."""
    import json

    if not isinstance(raw, str):
        return []
    s = raw.strip()
    if not s:
        return []
    try:
        data = json.loads(s)
    except Exception:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        arr = data.get('conceptos')
        if isinstance(arr, list):
            return [x for x in arr if isinstance(x, dict)]
    return []


def _formatear_items_concepto_libro(items):
    """Armar texto legible: Nombre — observaciones (omite 'sin observaciones')."""
    partes = []
    for it in items:
        nombre = str(it.get('nombre') or it.get('concepto') or it.get('descripcion') or '').strip()
        obs = str(it.get('observaciones') or '').strip()
        if obs.lower() in ('', 'sin observaciones', 'sin observaciones.'):
            obs = ''
        if nombre and obs:
            partes.append(f'{nombre} — {obs}')
        elif nombre:
            partes.append(nombre)
        elif obs:
            partes.append(obs)
    return '; '.join(partes)


def _descripcion_movimiento_libro(mov):
    """Texto legible para la columna Descripción del libro."""
    import re

    prefijo_contrato = ''
    items = []

    # 1) Preferir concepto_detalle (JSON completo de cobros de contrato).
    detalle_raw = (getattr(mov, 'concepto_detalle', None) or '').strip()
    if detalle_raw:
        items = _parse_items_concepto_json(detalle_raw)

    try:
        txt = (mov.concepto_sin_pipe_conceptos() or '').strip()
    except Exception:
        txt = (getattr(mov, 'concepto', None) or '').strip()
        if '|CONCEPTOS:' in txt:
            txt = txt.split('|CONCEPTOS:', 1)[0].strip()

    if not txt and not items:
        return f'Movimiento #{mov.id}'

    # Prefijo "Contrato #N" / "Operación N" si está en el texto.
    m_pref = re.match(
        r'^\s*((?:Contrato|Operaci[oó]n)\s*#?\s*\d+)\s*[-–—:]\s*(.*)$',
        txt or '',
        re.I | re.S,
    )
    resto = txt or ''
    if m_pref:
        prefijo_contrato = m_pref.group(1).strip()
        # Normalizar "Contrato #212"
        prefijo_contrato = re.sub(
            r'(?i)^(contrato)\s*#?\s*(\d+)$',
            r'Contrato #\2',
            prefijo_contrato,
        )
        prefijo_contrato = re.sub(
            r'(?i)^(operaci[oó]n)\s*#?\s*(\d+)$',
            r'Operación \2',
            prefijo_contrato,
        )
        resto = (m_pref.group(2) or '').strip()

    # 2) Si el resto (o el texto entero) es JSON con conceptos, parsearlo.
    if not items:
        candidatos = []
        if resto:
            candidatos.append(resto)
        if txt and txt not in candidatos:
            candidatos.append(txt)
        # A veces el JSON está truncado con "..." — intentar hasta el último ] o }.
        for cand in candidatos:
            parsed = _parse_items_concepto_json(cand)
            if parsed:
                items = parsed
                break
            for end_ch, open_ch in ((']', '['), ('}', '{')):
                if open_ch in cand and end_ch in cand:
                    try_s = cand[: cand.rfind(end_ch) + 1]
                    parsed = _parse_items_concepto_json(try_s)
                    if parsed:
                        items = parsed
                        break
            if items:
                break

    if items:
        cuerpo = _formatear_items_concepto_libro(items)
        if prefijo_contrato and cuerpo:
            return f'{prefijo_contrato} — {cuerpo}'
        if prefijo_contrato:
            return prefijo_contrato
        if cuerpo:
            return cuerpo

    # 3) Sin JSON: si el "resto" sigue siendo basura tipo [{...}], limpiar.
    if resto.lstrip().startswith(('[', '{')):
        return prefijo_contrato or f'Movimiento #{mov.id}'

    if prefijo_contrato and resto:
        return f'{prefijo_contrato} — {resto}'
    return txt or prefijo_contrato or f'Movimiento #{mov.id}'


def _fila_libro_desde_movimiento(mov, monto_prop_por_reserva=None, cotiz_por_reserva=None):
    """
    Mapea un MovimientoCaja a las columnas del libro.
    En ingresos de Operación N usa el monto al propietario (carátula/liquidación),
    no el total cobrado al locatario.
    """
    import re

    from inmobiliaria.models.caja import TipoMovimientoCajaEnum

    ars = Decimal(str(getattr(mov, 'monto_total', 0) or 0))
    usd = Decimal(str(getattr(mov, 'monto_dolares', 0) or 0))
    cotiz = getattr(mov, 'cotizacion_dolar', None)
    if cotiz is not None:
        cotiz = Decimal(str(cotiz))
        if cotiz <= 0:
            cotiz = None

    es_egreso = (getattr(mov, 'tipo', None) or '').strip().upper() == TipoMovimientoCajaEnum.EGRESO
    reserva_id = None
    es_operacion_libro = False

    # Ingreso de operación por día → solo lo del propietario (depto).
    if not es_egreso and monto_prop_por_reserva:
        conc = getattr(mov, 'concepto', None) or ''
        m_op = re.search(r'Operaci[oó]n\s*#?\s*(\d+)\b', conc, re.IGNORECASE)
        if m_op:
            rid = int(m_op.group(1))
            reserva_id = rid
            es_operacion_libro = True
            prop_share = monto_prop_por_reserva.get(rid)
            if prop_share is not None and prop_share >= 0:
                total_op = monto_prop_por_reserva.get(f'_total_{rid}')
                if total_op and total_op > 0 and ars > 0 and abs(ars - total_op) > Decimal('0.05'):
                    ars = (prop_share * ars / total_op).quantize(Decimal('0.01'))
                else:
                    ars = prop_share
                if usd > 0 and total_op and total_op > 0 and abs(usd - total_op) > Decimal('0.05'):
                    usd = (prop_share * usd / total_op).quantize(Decimal('0.01'))
                elif usd > 0:
                    usd = prop_share
            # Cotización guardada en el libro para esta operación (si el mov no tiene)
            if cotiz is None and cotiz_por_reserva:
                c_libro = cotiz_por_reserva.get(rid)
                if c_libro is not None:
                    c_libro = Decimal(str(c_libro))
                    if c_libro > 0:
                        cotiz = c_libro

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
        'sin_caja': False,
        'es_inicio_caja': False,
        'es_manual': False,
        'fila_manual_id': None,
        'es_operacion_libro': es_operacion_libro,
        'reserva_id': reserva_id,
    }


def _obtener_inicio_caja_libro(propiedad):
    """get_or_create del inicio de caja (fecha default 07/06/2026)."""
    from datetime import date

    inicio, _ = InicioCajaLibroPropiedad.objects.get_or_create(
        propiedad=propiedad,
        defaults={
            'fecha': date(2026, 6, 7),
            'gastos_ars': Decimal('0'),
            'alquileres_ars': Decimal('0'),
            'gastos_usd': Decimal('0'),
            'ingreso_usd': Decimal('0'),
        },
    )
    return inicio


def _obtener_costos_compra_libro(propiedad):
    """get_or_create de costos de compra (valor depto, escritura, honorarios)."""
    costos, _ = CostosCompraLibroPropiedad.objects.get_or_create(
        propiedad=propiedad,
        defaults={
            'valor_depto_comprado': Decimal('0'),
            'gastos_escritura': Decimal('0'),
            'honorarios_pagados': Decimal('0'),
        },
    )
    return costos


def _fila_inicio_caja_libro(inicio):
    """Fila del libro «Inicio de caja» — solo usa los montos de ese registro."""
    from datetime import datetime as dt
    from datetime import time as time_cls

    f_date = inicio.fecha
    f_dt = dt.combine(f_date, time_cls.min)
    if timezone.is_naive(f_dt):
        try:
            f_dt = timezone.make_aware(f_dt)
        except Exception:
            pass
    cotiz = getattr(inicio, 'tipo_cambio', None)
    if cotiz is not None:
        cotiz = Decimal(str(cotiz))
        if cotiz <= 0:
            cotiz = None
    return {
        'fecha': f_dt,
        'descripcion': 'Inicio de caja',
        'gastos_ars': Decimal(str(inicio.gastos_ars or 0)),
        'alquileres_ars': Decimal(str(inicio.alquileres_ars or 0)),
        'gastos_usd': Decimal(str(inicio.gastos_usd or 0)),
        'ingreso_usd': Decimal(str(inicio.ingreso_usd or 0)),
        'tipo_cambio': cotiz,
        'movimiento_id': None,
        'tipo': 'INICIO',
        'sin_caja': False,
        'es_inicio_caja': True,
        'es_manual': False,
        'fila_manual_id': None,
    }


def _fila_desde_manual(fila):
    """Fila del libro desde una anotación manual editable."""
    from datetime import datetime as dt
    from datetime import time as time_cls

    f_date = fila.fecha
    f_dt = dt.combine(f_date, time_cls.min)
    if timezone.is_naive(f_dt):
        try:
            f_dt = timezone.make_aware(f_dt)
        except Exception:
            pass
    cotiz = getattr(fila, 'tipo_cambio', None)
    if cotiz is not None:
        cotiz = Decimal(str(cotiz))
        if cotiz <= 0:
            cotiz = None
    return {
        'fecha': f_dt,
        'descripcion': (fila.descripcion or '').strip() or 'Anotación manual',
        'gastos_ars': Decimal(str(fila.gastos_ars or 0)),
        'alquileres_ars': Decimal(str(fila.alquileres_ars or 0)),
        'gastos_usd': Decimal(str(fila.gastos_usd or 0)),
        'ingreso_usd': Decimal(str(fila.ingreso_usd or 0)),
        'tipo_cambio': cotiz,
        'movimiento_id': None,
        'tipo': 'MANUAL',
        'sin_caja': False,
        'es_inicio_caja': False,
        'es_manual': True,
        'fila_manual_id': fila.id,
    }


def _propiedad_en_cartera_oficina(user, propiedad_id):
    sucursal = getattr(user, 'sucursal', None)
    if not sucursal:
        return None, False
    titular = usuario_titular_cartera(sucursal)
    en_cartera = bool(
        titular
        and CarteraPropiedadUsuario.objects.filter(
            usuario=titular,
            propiedad_id=propiedad_id,
            propiedad__sucursal=sucursal,
        ).exists()
    )
    return sucursal, en_cartera


def _parse_montos_fila_manual(request):
    from inmobiliaria.decimal_utils import parse_decimal_monto

    fecha = _parse_fecha((request.POST.get('fecha') or '').strip())
    descripcion = (request.POST.get('descripcion') or '').strip()[:255]
    gastos_ars = parse_decimal_monto(request.POST.get('gastos_ars', '0'))
    alquileres_ars = parse_decimal_monto(request.POST.get('alquileres_ars', '0'))
    gastos_usd = parse_decimal_monto(request.POST.get('gastos_usd', '0'))
    ingreso_usd = parse_decimal_monto(request.POST.get('ingreso_usd', '0'))
    cotiz_raw = (request.POST.get('tipo_cambio') or '').strip()
    tipo_cambio = parse_decimal_monto(cotiz_raw) if cotiz_raw else None
    if tipo_cambio is not None and tipo_cambio <= 0:
        tipo_cambio = None
    return {
        'fecha': fecha,
        'descripcion': descripcion,
        'gastos_ars': gastos_ars.quantize(Decimal('0.01')),
        'alquileres_ars': alquileres_ars.quantize(Decimal('0.01')),
        'gastos_usd': gastos_usd.quantize(Decimal('0.01')),
        'ingreso_usd': ingreso_usd.quantize(Decimal('0.01')),
        'tipo_cambio': tipo_cambio.quantize(Decimal('0.01')) if tipo_cambio else None,
    }


@login_required
def oficina_propiedades_lista(request):
    """Listado de departamentos de oficina = cartera compartida de la sucursal."""
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
    """Libro automático (estilo planilla) de movimientos de caja de un depto de la cartera."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    from inmobiliaria.models import Propiedad

    sucursal = request.user.sucursal
    titular = sincronizar_cartera_compartida_sucursal(sucursal)
    en_cartera = bool(
        titular
        and CarteraPropiedadUsuario.objects.filter(
            usuario=titular,
            propiedad_id=propiedad_id,
            propiedad__sucursal=sucursal,
        ).exists()
    )
    if not en_cartera:
        return HttpResponseForbidden()

    propiedad = get_object_or_404(
        Propiedad.objects.select_related('propietario'),
        pk=propiedad_id,
        sucursal=sucursal,
    )

    fecha_desde_s = (request.GET.get('fecha_desde') or '').strip()
    fecha_hasta_s = (request.GET.get('fecha_hasta') or '').strip()
    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    inicio = _obtener_inicio_caja_libro(propiedad)
    costos = _obtener_costos_compra_libro(propiedad)

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
        from inmobiliaria.models import Reserva

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
        _fila_libro_desde_movimiento(
            m,
            monto_prop_por_reserva=monto_prop_por_reserva,
            cotiz_por_reserva=cotiz_por_reserva,
        )
        for m in movimientos
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

    filas.sort(
        key=lambda f: (
            f.get('fecha') or timezone.now(),
            0 if f.get('es_inicio_caja') else 1,
            f.get('movimiento_id') or 0,
        )
    )

    # Inicio de caja siempre al tope del libro (uno por depto, editable).
    filas.insert(0, _fila_inicio_caja_libro(inicio))

    totales = {
        'gastos_ars': sum((f['gastos_ars'] for f in filas), Decimal('0')),
        'alquileres_ars': sum((f['alquileres_ars'] for f in filas), Decimal('0')),
        'gastos_usd': sum((f['gastos_usd'] for f in filas), Decimal('0')),
        'ingreso_usd': sum((f['ingreso_usd'] for f in filas), Decimal('0')),
    }
    totales['balance_ars'] = totales['alquileres_ars'] - totales['gastos_ars']
    totales['balance_usd'] = totales['ingreso_usd'] - totales['gastos_usd']

    suma_usd_libro = totales['gastos_usd'] + totales['ingreso_usd']
    subtotal_costos = (
        costos.valor_depto_comprado
        + costos.gastos_escritura
        + costos.honorarios_pagados
    )
    resumen = {
        'valor_depto_comprado': costos.valor_depto_comprado,
        'gastos_escritura': costos.gastos_escritura,
        'honorarios_pagados': costos.honorarios_pagados,
        'subtotal_costos': subtotal_costos,
        'gastos_usd': totales['gastos_usd'],
        'ingreso_usd': totales['ingreso_usd'],
        'suma_usd_libro': suma_usd_libro,
        'total': subtotal_costos + suma_usd_libro,
    }

    otras = list(_qs_propiedades_oficina(sucursal, request.user))

    return render(
        request,
        'inmobiliaria/oficina/propiedad_libro.html',
        {
            'propiedad': propiedad,
            'filas': filas,
            'totales': totales,
            'resumen': resumen,
            'costos_compra': costos,
            'otras_propiedades': otras,
            'fecha_desde': fecha_desde_s,
            'fecha_hasta': fecha_hasta_s,
            'inicio_caja': inicio,
        },
    )


@login_required
@require_POST
def oficina_propiedad_libro_inicio_caja(request, propiedad_id):
    """Guarda el inicio de caja (solo la fila Inicio de caja de ese depto)."""
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.decimal_utils import format_monto_argentino, parse_decimal_monto
    from inmobiliaria.models import Propiedad

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    inicio = _obtener_inicio_caja_libro(propiedad)


    fecha_s = (request.POST.get('fecha') or '').strip()
    fecha = _parse_fecha(fecha_s)
    if not fecha:
        return JsonResponse({'ok': False, 'error': 'Fecha inválida.'}, status=400)

    try:
        gastos_ars = parse_decimal_monto(request.POST.get('gastos_ars', '0'))
        alquileres_ars = parse_decimal_monto(request.POST.get('alquileres_ars', '0'))
        gastos_usd = parse_decimal_monto(request.POST.get('gastos_usd', '0'))
        ingreso_usd = parse_decimal_monto(request.POST.get('ingreso_usd', '0'))
        cotiz_raw = (request.POST.get('tipo_cambio') or '').strip()
        tipo_cambio = parse_decimal_monto(cotiz_raw) if cotiz_raw else None
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Monto inválido.'}, status=400)

    if tipo_cambio is not None and tipo_cambio <= 0:
        tipo_cambio = None

    # Compatibilidad: si mandan los campos viejos monto_ars / monto_usd
    if (
        not any(
            abs(x) > 0
            for x in (gastos_ars, alquileres_ars, gastos_usd, ingreso_usd)
        )
        and (request.POST.get('monto_ars') or request.POST.get('monto_usd'))
    ):
        try:
            monto_ars = parse_decimal_monto(request.POST.get('monto_ars', '0'))
            monto_usd = parse_decimal_monto(request.POST.get('monto_usd', '0'))
        except Exception:
            monto_ars = Decimal('0')
            monto_usd = Decimal('0')
        if monto_ars >= 0:
            alquileres_ars = monto_ars
        else:
            gastos_ars = abs(monto_ars)
        if monto_usd >= 0:
            ingreso_usd = monto_usd
        else:
            gastos_usd = abs(monto_usd)

    inicio.fecha = fecha
    inicio.gastos_ars = gastos_ars.quantize(Decimal('0.01'))
    inicio.alquileres_ars = alquileres_ars.quantize(Decimal('0.01'))
    inicio.gastos_usd = gastos_usd.quantize(Decimal('0.01'))
    inicio.ingreso_usd = ingreso_usd.quantize(Decimal('0.01'))
    inicio.tipo_cambio = tipo_cambio.quantize(Decimal('0.01')) if tipo_cambio else None
    inicio.actualizado_por = request.user
    inicio.save()

    return JsonResponse(
        {
            'ok': True,
            'fecha': inicio.fecha.isoformat(),
            'fecha_display': inicio.fecha.strftime('%d/%m/%Y'),
            'gastos_ars': str(inicio.gastos_ars),
            'alquileres_ars': str(inicio.alquileres_ars),
            'gastos_usd': str(inicio.gastos_usd),
            'ingreso_usd': str(inicio.ingreso_usd),
            'gastos_ars_fmt': format_monto_argentino(inicio.gastos_ars),
            'alquileres_ars_fmt': format_monto_argentino(inicio.alquileres_ars),
            'gastos_usd_fmt': format_monto_argentino(inicio.gastos_usd),
            'ingreso_usd_fmt': format_monto_argentino(inicio.ingreso_usd),
        }
    )


@login_required
@require_POST
def oficina_propiedad_libro_costos_compra(request, propiedad_id):
    """Guarda valor depto comprado, escritura y honorarios de este depto."""
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.decimal_utils import format_monto_argentino, parse_decimal_monto
    from inmobiliaria.models import Propiedad

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    costos = _obtener_costos_compra_libro(propiedad)

    try:
        valor = parse_decimal_monto(request.POST.get('valor_depto_comprado', '0'))
        escritura = parse_decimal_monto(request.POST.get('gastos_escritura', '0'))
        honorarios = parse_decimal_monto(request.POST.get('honorarios_pagados', '0'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Monto inválido.'}, status=400)

    costos.valor_depto_comprado = valor.quantize(Decimal('0.01'))
    costos.gastos_escritura = escritura.quantize(Decimal('0.01'))
    costos.honorarios_pagados = honorarios.quantize(Decimal('0.01'))
    costos.actualizado_por = request.user
    costos.save()

    return JsonResponse(
        {
            'ok': True,
            'valor_depto_comprado': format_monto_argentino(costos.valor_depto_comprado),
            'gastos_escritura': format_monto_argentino(costos.gastos_escritura),
            'honorarios_pagados': format_monto_argentino(costos.honorarios_pagados),
        }
    )


@login_required
@require_POST
def oficina_propiedad_libro_fila_manual(request, propiedad_id):
    """Crea o actualiza una anotación manual (las 4 columnas del libro)."""
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.models import Propiedad

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)

    try:
        datos = _parse_montos_fila_manual(request)
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Datos inválidos.'}, status=400)

    if not datos['fecha']:
        return JsonResponse({'ok': False, 'error': 'Fecha inválida.'}, status=400)

    if (
        datos['gastos_ars'] == 0
        and datos['alquileres_ars'] == 0
        and datos['gastos_usd'] == 0
        and datos['ingreso_usd'] == 0
    ):
        return JsonResponse(
            {'ok': False, 'error': 'Cargá al menos un monto en alguna columna.'},
            status=400,
        )

    fila_id = (request.POST.get('fila_id') or '').strip()
    if fila_id:
        if not fila_id.isdigit():
            return JsonResponse({'ok': False, 'error': 'Fila inválida.'}, status=400)
        fila = get_object_or_404(
            FilaManualLibroPropiedad,
            pk=int(fila_id),
            propiedad=propiedad,
        )
        for k, v in datos.items():
            setattr(fila, k, v)
        fila.save()
    else:
        fila = FilaManualLibroPropiedad.objects.create(
            propiedad=propiedad,
            creado_por=request.user,
            **datos,
        )

    return JsonResponse({'ok': True, 'fila_id': fila.id})


@login_required
@require_POST
def oficina_propiedad_libro_fila_manual_eliminar(request, propiedad_id):
    """Elimina una anotación manual del libro."""
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.models import Propiedad

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    fila_id = (request.POST.get('fila_id') or '').strip()
    if not fila_id.isdigit():
        return JsonResponse({'ok': False, 'error': 'Fila inválida.'}, status=400)

    deleted, _ = FilaManualLibroPropiedad.objects.filter(
        pk=int(fila_id),
        propiedad=propiedad,
    ).delete()
    if not deleted:
        return JsonResponse({'ok': False, 'error': 'No se encontró la fila.'}, status=404)
    return JsonResponse({'ok': True})


@login_required
@require_POST
def oficina_propiedad_libro_actualizar_cotizacion(request, propiedad_id):
    """
    Completa cotización USD en un movimiento de caja o en una operación del libro
    (fila «op.» sin movimiento): calcula Ingreso/Gastos en dólar.
    """
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.decimal_utils import format_monto_argentino, parse_decimal_monto
    from inmobiliaria.models import MovimientoCaja, Propiedad, Reserva

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)

    cotiz_raw = (request.POST.get('cotizacion_dolar') or '').strip()
    try:
        cotiz = parse_decimal_monto(cotiz_raw) if cotiz_raw else None
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Cotización inválida.'}, status=400)
    if cotiz is None or cotiz <= 0:
        return JsonResponse({'ok': False, 'error': 'Indicá un tipo de cambio válido.'}, status=400)
    cotiz = cotiz.quantize(Decimal('0.01'))

    def _fmt(v):
        if not v:
            return ''
        return format_monto_argentino(v)

    # --- Operación del libro (sin movimiento de caja) ---
    reserva_id = (request.POST.get('reserva_id') or '').strip()
    if reserva_id.isdigit():
        reserva = Reserva.objects.filter(
            pk=int(reserva_id),
            propiedad=propiedad,
            sucursal=sucursal,
            eliminada=False,
        ).first()
        if not reserva:
            return JsonResponse({'ok': False, 'error': 'Operación no encontrada.'}, status=404)

        CotizacionLibroOperacion.objects.update_or_create(
            reserva=reserva,
            defaults={
                'cotizacion_dolar': cotiz,
                'actualizado_por': request.user,
            },
        )

        liq = _liquidaciones_por_reserva([reserva.id]).get(reserva.id)
        monto_prop = _monto_propietario_reserva_libro(reserva, liq)
        moneda = (getattr(reserva, 'moneda', None) or 'ARS').strip().upper()
        gastos_usd = Decimal('0')
        ingreso_usd = Decimal('0')
        alquileres_ars = Decimal('0')
        if moneda == 'USD':
            ingreso_usd = monto_prop
            alquileres_ars = (monto_prop * cotiz).quantize(Decimal('0.01'))
        else:
            alquileres_ars = monto_prop
            ingreso_usd = (monto_prop / cotiz).quantize(Decimal('0.01'))

        return JsonResponse({
            'ok': True,
            'reserva_id': reserva.id,
            'gastos_usd': _fmt(gastos_usd),
            'ingreso_usd': _fmt(ingreso_usd),
            'alquileres_ars': _fmt(alquileres_ars),
            'tipo_cambio': _fmt(cotiz),
            'tipo': 'IN',
            'message': 'Cotización de la operación guardada.',
        })

    # --- Movimiento de caja ---
    mov_id = (request.POST.get('movimiento_id') or '').strip()
    if not mov_id.isdigit():
        return JsonResponse({'ok': False, 'error': 'Movimiento u operación inválidos.'}, status=400)

    movimiento = MovimientoCaja.objects.filter(
        pk=int(mov_id),
        propiedad=propiedad,
        sucursal=sucursal,
        fecha_eliminacion__isnull=True,
    ).first()
    if not movimiento:
        # Puede ser un ingreso de operación vinculado por concepto sin FK propiedad correcta:
        # igual permitir si el concepto menciona una reserva de esta propiedad.
        movimiento = MovimientoCaja.objects.filter(
            pk=int(mov_id),
            sucursal=sucursal,
            fecha_eliminacion__isnull=True,
        ).first()
        if not movimiento:
            return JsonResponse({'ok': False, 'error': 'Movimiento no encontrado.'}, status=404)

    usd_raw = (request.POST.get('monto_dolares') or '').strip()
    try:
        usd_in = parse_decimal_monto(usd_raw) if usd_raw else None
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Monto USD inválido.'}, status=400)
    if usd_in is not None and usd_in <= 0:
        usd_in = None

    ars = Decimal(str(getattr(movimiento, 'monto_total', 0) or 0))
    usd_actual = Decimal(str(getattr(movimiento, 'monto_dolares', 0) or 0))

    if cotiz and ars > 0 and (usd_in is None) and usd_actual <= 0:
        usd_in = (ars / cotiz).quantize(Decimal('0.01'))

    updates = ['cotizacion_dolar']
    movimiento.cotizacion_dolar = cotiz
    if usd_in is not None:
        movimiento.monto_dolares = usd_in.quantize(Decimal('0.01'))
        updates.append('monto_dolares')
    movimiento.save(update_fields=updates)

    # Si es operación, también guardar cotización de libro (para el monto propietario).
    import re
    conc = movimiento.concepto or ''
    m_op = re.search(r'Operaci[oó]n\s*#?\s*(\d+)\b', conc, re.IGNORECASE)
    if m_op:
        rid = int(m_op.group(1))
        if Reserva.objects.filter(pk=rid, propiedad=propiedad).exists():
            CotizacionLibroOperacion.objects.update_or_create(
                reserva_id=rid,
                defaults={
                    'cotizacion_dolar': cotiz,
                    'actualizado_por': request.user,
                },
            )

    fila = _fila_libro_desde_movimiento(movimiento)
    return JsonResponse({
        'ok': True,
        'movimiento_id': movimiento.id,
        'gastos_usd': _fmt(fila['gastos_usd']),
        'ingreso_usd': _fmt(fila['ingreso_usd']),
        'tipo_cambio': _fmt(fila['tipo_cambio']),
        'tipo': fila['tipo'],
        'message': 'Cotización guardada.',
    })
