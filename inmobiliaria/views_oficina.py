"""Módulo Oficina: gastos, categorías y acceso a honorarios, vales, comisiones y cartera."""
import logging
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, ProtectedError, Sum
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
    OperacionVenta,
    PersonaOficina,
    ValeVendedor,
)
from inmobiliaria.models.persona import usuario_es_nivel_administracion
from inmobiliaria.oficina_gastos import (
    asegurar_categoria_vales,
    asegurar_estructura_cierre_oficina,
    propagar_categoria_oficina_a_espejos,
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


_RE_OPERACION_ANULADA = re.compile(
    r'operaci[oó]n\s+anulada|operacion\s+anulada',
    re.IGNORECASE,
)

# Cobros mal vinculados que no deben aparecer en libros de oficina (desconfiguran totales).
_MOVIMIENTOS_EXCLUIDOS_LIBRO_OFICINA = frozenset({4441})


def _concepto_es_operacion_anulada(concepto):
    """True si el movimiento es un contrasiento de operación anulada."""
    return bool(_RE_OPERACION_ANULADA.search(concepto or ''))


def _movimiento_excluido_libro_oficina(mov, propiedad=None):
    """True si el movimiento no debe figurar en ningún / este libro de oficina."""
    try:
        mid = int(getattr(mov, 'id', 0) or 0)
    except (TypeError, ValueError):
        return False
    if mid in _MOVIMIENTOS_EXCLUIDOS_LIBRO_OFICINA:
        return True
    if propiedad is not None and _movimiento_ajeno_al_libro(mov, propiedad):
        return True
    return False


def _ids_operaciones_contratos_propiedad(propiedad, sucursal):
    """IDs de reservas (operaciones) y contratos vigentes de la propiedad."""
    from inmobiliaria.models import ContratoAlquiler, Reserva

    reserva_ids = list(
        Reserva.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
            eliminada=False,
        )
        .exclude(estado='cancelada')
        .values_list('id', flat=True)[:800]
    )
    contrato_ids = list(
        ContratoAlquiler.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
        )
        .exclude(estado='rescindido')
        .values_list('id', flat=True)[:400]
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


def _movimiento_ajeno_al_libro(mov, propiedad):
    """
    True si el movimiento no debe figurar en el libro de este depto.
    Ej.: MovimientoCaja mal asignado al FK pero con recibo de otra propiedad.
    """
    prop_id = getattr(propiedad, 'pk', None) or getattr(propiedad, 'id', None)
    if not prop_id or not mov:
        return False
    try:
        rec = getattr(mov, 'recibo', None)
    except Exception:
        rec = None
    if rec is not None:
        rec_prop = getattr(rec, 'propiedad_id', None)
        if rec_prop and str(rec_prop) != str(prop_id):
            return True
        try:
            reserva = getattr(rec, 'reserva', None)
        except Exception:
            reserva = None
        if reserva is not None:
            rprop = getattr(reserva, 'propiedad_id', None)
            if rprop and str(rprop) != str(prop_id):
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
    ).select_related('recibo', 'recibo__reserva')
    if dr_desde:
        base = base.filter(fecha__date__gte=dr_desde)
    if dr_hasta:
        base = base.filter(fecha__date__lte=dr_hasta)

    # 1) Directos por FK propiedad (sin contrasientos de operación anulada
    #    ni movimientos cuyo recibo pertenece a otro depto).
    por_prop = []
    for m in base.filter(propiedad=propiedad).order_by('fecha', 'id')[:2000]:
        if _concepto_es_operacion_anulada(getattr(m, 'concepto', None)):
            continue
        if _movimiento_excluido_libro_oficina(m, propiedad):
            continue
        por_prop.append(m)
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
            conc = getattr(mov, 'concepto', None) or ''
            if _concepto_es_operacion_anulada(conc):
                continue
            if _movimiento_excluido_libro_oficina(mov, propiedad):
                continue
            # No meter cobros de otro depto solo porque el texto menciona una op.
            mov_prop = getattr(mov, 'propiedad_id', None)
            if mov_prop and str(mov_prop) != str(propiedad.id):
                continue
            if _movimiento_refiere_operacion_o_contrato(conc, reserva_ids, contrato_ids):
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
    Las operaciones no se inventan desde cobros/caja.
    Entran al libro solo con liquidación confirmada
    (ver _filas_liquidaciones_confirmadas_libro).
    """
    return []


def _filas_contratos_faltantes_libro(
    propiedad,
    sucursal,
    contrato_ids,
    movimientos,
    dr_desde=None,
    dr_hasta=None,
):
    """
    Los cobros de contrato no se inventan desde cuotas/movimientos.
    Entran al libro solo con liquidación confirmada
    (ver _filas_liquidaciones_confirmadas_libro).
    """
    return []


_MESES_LIBRO_ES = (
    '',
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
)


def _periodo_liquidacion_libro(liq):
    """Etiqueta de período (ej. «Septiembre de 2026») desde fecha_desde de la liquidación."""
    fd = getattr(liq, 'fecha_desde', None)
    if not fd:
        return ''
    try:
        return f'{_MESES_LIBRO_ES[fd.month]} de {fd.year}'
    except Exception:
        return ''


def _descripcion_liquidacion_oficina_libro(liq):
    """Texto de fila: Contrato/Operación + conceptos de alquiler de la liquidación."""
    from inmobiliaria.liquidacion_operacion import info_operacion_liquidacion

    info = info_operacion_liquidacion(liq)
    ref = (info.get('operacion_ref') or '').strip()
    if not ref or ref == '—':
        if getattr(liq, 'contrato_id', None):
            ref = f'Contrato #{liq.contrato_id}'
        elif getattr(liq, 'reserva_id', None):
            ref = f'Operación {liq.reserva_id}'
        else:
            ref = f'Liquidación #{liq.id}'
    # Mantener "Contrato #N" / "Operación N"
    ref = re.sub(r'(?i)^contrato\s*#?\s*(\d+)$', r'Contrato #\1', ref)
    ref = re.sub(r'(?i)^reserva\s*#?\s*(\d+)$', r'Operación \1', ref)

    # Preferir descripciones de las operaciones incluidas (alquileres del depto)
    detalles = []
    for op in (getattr(liq, 'operaciones_incluidas', None) or []):
        if not isinstance(op, dict):
            continue
        tipo = (op.get('tipo') or '').strip().lower()
        if tipo in ('division',):
            continue
        # Honorarios/comisiones de inmobiliaria no son «lo del depto»
        if tipo == 'contrato_operacion_principal' or op.get('es_operacion_principal_honorarios'):
            continue
        d = (
            op.get('descripcion')
            or op.get('concepto_pago')
            or op.get('label')
            or ''
        ).strip()
        if d:
            # Acortar prefijo repetido "Contrato #N — "
            d = re.sub(r'(?i)^contrato\s*#?\s*\d+\s*[—\-–]\s*', '', d).strip() or d
            if d and d not in detalles:
                detalles.append(d)
        if len(detalles) >= 4:
            break

    if detalles:
        return f'{ref} — ' + '; '.join(detalles)

    periodo = _periodo_liquidacion_libro(liq)
    if periodo:
        return f'{ref} — Alquiler a pagar // {periodo}'
    return f'{ref} — Alquiler a pagar'


# Estados de liquidación que acreditan alquiler en el libro del depto.
_ESTADOS_LIQUIDACION_LIBRO = ('oficina', 'pagada', 'cerrada', 'procesada')


def _filas_liquidaciones_oficina_libro(
    propiedad,
    sucursal,
    movimientos=None,
    dr_desde=None,
    dr_hasta=None,
):
    """Alias: liquidaciones confirmadas en el mes del período."""
    return _filas_liquidaciones_confirmadas_libro(
        propiedad, sucursal, movimientos=movimientos, dr_desde=dr_desde, dr_hasta=dr_hasta
    )


def _filas_liquidaciones_confirmadas_libro(
    propiedad,
    sucursal,
    movimientos=None,
    dr_desde=None,
    dr_hasta=None,
):
    """
    Liquidaciones confirmadas (oficina / pagada / cerrada / procesada):
    se acreditan en el libro del depto en el mes de su período (fecha_desde),
    con el monto del propietario — no el total cobrado al locatario.
    Sin liquidación confirmada, la operación/contrato no aparece.
    """
    from datetime import time as time_cls

    from inmobiliaria.models import LiquidacionPropietario

    qs = (
        LiquidacionPropietario.objects.filter(
            propiedad=propiedad,
            sucursal=sucursal,
            estado__in=_ESTADOS_LIQUIDACION_LIBRO,
        )
        .exclude(reserva__eliminada=True)
        .exclude(reserva__estado='cancelada')
        .exclude(contrato__estado='rescindido')
        .select_related('contrato', 'reserva', 'reserva__cliente', 'contrato__inquilino')
        .order_by('fecha_desde', 'id')
    )

    filas = []
    for liq in qs:
        # Mes que le corresponde = período de la liquidación (fecha_desde).
        fecha_raw = (
            getattr(liq, 'fecha_desde', None)
            or getattr(liq, 'fecha_procesamiento', None)
            or getattr(liq, 'fecha_creacion', None)
        )
        if fecha_raw is None:
            continue
        if isinstance(fecha_raw, datetime):
            f_dt = fecha_raw
            try:
                if timezone.is_aware(f_dt):
                    f_date = timezone.localtime(f_dt).date()
                else:
                    f_date = f_dt.date()
            except Exception:
                f_date = f_dt.date()
        elif isinstance(fecha_raw, date):
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

        moneda = (getattr(liq, 'moneda', None) or 'ARS').strip().upper()
        # Solo lo del depto/propietario (nunca el total cobrado al inquilino).
        monto = Decimal(str(getattr(liq, 'monto_propietario', None) or 0))
        if monto <= 0:
            monto = Decimal(str(getattr(liq, 'monto_a_pagar', None) or 0))
        if monto <= 0:
            continue

        cotiz = getattr(liq, 'cotizacion_dolar', None)
        if cotiz is not None:
            cotiz = Decimal(str(cotiz))
            if cotiz <= 0:
                cotiz = None

        fila = {
            'fecha': f_dt,
            'descripcion': _descripcion_liquidacion_oficina_libro(liq),
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
            'es_liquidacion_oficina': True,
            'liquidacion_id': liq.id,
            'reserva_id': getattr(liq, 'reserva_id', None),
            'observaciones': (getattr(liq, 'observaciones', None) or '').strip(),
            'clasificacion_libro': (getattr(liq, 'clasificacion_libro', None) or '').strip(),
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

    ventas_mes = OperacionVenta.objects.filter(
        sucursal=sucursal,
        estado='confirmada',
        fecha_venta__gte=mes_ini,
        fecha_venta__lte=today,
    )
    ventas_mes_count = ventas_mes.count()
    ventas_mes_usd = ventas_mes.aggregate(t=Sum('precio_usd'))['t'] or Decimal('0')

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
            'ventas_mes_count': ventas_mes_count,
            'ventas_mes_usd': ventas_mes_usd,
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

    return render(
        request,
        'inmobiliaria/oficina/categorias.html',
        {
            'arbol': _arbol_categorias_admin(sucursal),
        },
    )


@login_required
@require_POST
def oficina_categoria_mover(request, categoria_id):
    """Sube o baja una categoría (raíz o subcategoría) respecto a sus hermanas."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    direccion = (request.POST.get('direccion') or '').strip().lower()
    if direccion not in ('up', 'down'):
        messages.error(request, 'Dirección de movimiento inválida.')
        return redirect('inmobiliaria:oficina_categorias')

    cat = get_object_or_404(
        CategoriaGastoOficina,
        id=categoria_id,
        sucursal=request.user.sucursal,
    )
    hermanos = list(
        CategoriaGastoOficina.objects.filter(
            sucursal=cat.sucursal,
            parent=cat.parent,
        ).order_by('orden', 'nombre', 'id')
    )
    idx = next((i for i, c in enumerate(hermanos) if c.id == cat.id), None)
    if idx is None:
        return redirect('inmobiliaria:oficina_categorias')

    swap_idx = idx - 1 if direccion == 'up' else idx + 1
    if swap_idx < 0 or swap_idx >= len(hermanos):
        return redirect('inmobiliaria:oficina_categorias')

    hermanos[idx], hermanos[swap_idx] = hermanos[swap_idx], hermanos[idx]
    for i, hermana in enumerate(hermanos):
        if hermana.orden != i:
            hermana.orden = i
            hermana.save(update_fields=['orden'])
            if not hermana.vendedor_id:
                propagar_categoria_oficina_a_espejos(hermana, accion='upsert')

    return redirect('inmobiliaria:oficina_categorias')


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

    try:
        resumen = construir_resumen_cierre(sucursal, anio, mes)
    except Exception:
        logger.exception(
            'oficina_resumen_cierre: error armando resumen (sucursal_id=%s, %s-%02d)',
            getattr(sucursal, 'pk', None),
            anio,
            mes,
        )
        messages.error(
            request,
            'No se pudo armar el resumen de cierre. Probá de nuevo; si sigue fallando, avisá a sistemas.',
        )
        return redirect('inmobiliaria:oficina_dashboard')

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


@login_required
def oficina_reporte_deptos_mensual(request):
    """
    Planilla mensual de todos los departamentos de oficina.
    Los saldos negativos no suman al total y se arrastran al mes siguiente.
    """
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')

    from inmobiliaria.oficina_reporte_deptos import construir_reporte_mensual_deptos_oficina

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

    try:
        reporte = construir_reporte_mensual_deptos_oficina(sucursal, anio, mes)
    except Exception:
        logger.exception(
            'oficina_reporte_deptos_mensual: error (sucursal_id=%s, %s-%02d)',
            getattr(sucursal, 'pk', None),
            anio,
            mes,
        )
        messages.error(
            request,
            'No se pudo armar el reporte de departamentos. Probá de nuevo; si sigue fallando, avisá a sistemas.',
        )
        return redirect('inmobiliaria:oficina_dashboard')

    anios_opts = list(range(today.year - 2, today.year + 2))
    meses_opts = list(enumerate(
        ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
         'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'],
        start=1,
    ))

    return render(
        request,
        'inmobiliaria/oficina/reporte_deptos_mensual.html',
        {
            'reporte': reporte,
            'anio': anio,
            'mes': mes,
            'anios_opts': anios_opts,
            'meses_opts': meses_opts,
        },
    )


def _clave_orden_piso(piso):
    """Orden natural de piso: PB → 0, luego 1, 2, 10… (no alfabético '10' antes de '2')."""
    s = (piso or '').strip().upper().replace('.', '')
    if not s:
        return (2, 9999, '')
    if s in ('PB', 'PLANTA BAJA', 'PBAJA', '0', 'PBJA'):
        return (0, 0, s)
    m = re.match(r'^(\d+)', s)
    if m:
        return (1, int(m.group(1)), s)
    return (1, 9998, s)


def _clave_orden_depto(departamento):
    """Orden natural de departamento: números luego letras."""
    s = (departamento or '').strip().upper()
    if not s:
        return (2, 9999, '')
    m = re.match(r'^(\d+)', s)
    if m:
        return (0, int(m.group(1)), s)
    return (1, 0, s)


def _ordenar_propiedades_oficina(propiedades, orden='direccion'):
    """
    orden='direccion' → calle, piso, dpto
    orden='piso' → piso, dpto, calle
    orden='propietario' → propietario, calle, piso, dpto
    """
    items = list(propiedades)
    if orden == 'piso':
        items.sort(
            key=lambda p: (
                _clave_orden_piso(getattr(p, 'piso', None)),
                _clave_orden_depto(getattr(p, 'departamento', None)),
                (getattr(p, 'direccion', None) or '').strip().lower(),
                p.id,
            )
        )
    elif orden == 'propietario':
        items.sort(
            key=lambda p: (
                str(getattr(p, 'propietario', None) or '').strip().lower(),
                (getattr(p, 'direccion', None) or '').strip().lower(),
                _clave_orden_piso(getattr(p, 'piso', None)),
                _clave_orden_depto(getattr(p, 'departamento', None)),
                p.id,
            )
        )
    else:
        items.sort(
            key=lambda p: (
                (getattr(p, 'direccion', None) or '').strip().lower(),
                _clave_orden_piso(getattr(p, 'piso', None)),
                _clave_orden_depto(getattr(p, 'departamento', None)),
                p.id,
            )
        )
    return items


def _filtrar_propiedades_oficina(propiedades, q):
    """Filtra por id, dirección/piso/dpto o nombre de propietario."""
    texto = (q or '').strip().lower()
    if not texto:
        return list(propiedades)
    tokens = [t for t in texto.split() if t]
    out = []
    for p in propiedades:
        prop = str(getattr(p, 'propietario', None) or '').strip().lower()
        haystack = ' '.join(
            [
                str(getattr(p, 'id', '') or ''),
                (getattr(p, 'direccion', None) or '').strip().lower(),
                str(getattr(p, 'piso', None) or '').strip().lower(),
                str(getattr(p, 'departamento', None) or '').strip().lower(),
                prop,
            ]
        )
        if all(t in haystack for t in tokens):
            out.append(p)
    return out


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
    """Armar texto legible: Nombre — observaciones (omite 'sin observaciones' e IDs)."""
    partes = []
    for it in items:
        nombre = str(it.get('nombre') or it.get('concepto') or it.get('descripcion') or '').strip()
        nombre = _quitar_id_concepto_de_texto(nombre)
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


def _quitar_id_concepto_de_texto(texto):
    """Quita prefijos tipo '44 — ELECTRICISTA' → 'ELECTRICISTA'."""
    import re

    t = (texto or '').strip()
    if not t:
        return ''
    # Varias veces por si viene "5 — 10 — Nombre"
    for _ in range(3):
        nuevo = re.sub(r'^\s*\d+\s*[—–\-:]\s*', '', t)
        if nuevo == t:
            break
        t = nuevo.strip()
    return t


def _variantes_direccion_propiedad_libro(prop):
    """Textos de dirección/unidad que no deben figurar en la descripción del libro."""
    if not prop:
        return []
    dir_ = (getattr(prop, 'direccion', None) or '').strip()
    if not dir_:
        return []
    piso = (getattr(prop, 'piso', None) or '').strip()
    depto = (getattr(prop, 'departamento', None) or '').strip()
    variantes = {dir_}
    if piso and depto:
        variantes.add(f'{dir_} {piso}/{depto}')
        variantes.add(f'{dir_}{piso}/{depto}')
        variantes.add(f'{dir_} {piso}º {depto}')
        variantes.add(f'{dir_} {piso}° {depto}')
        variantes.add(f'{dir_} {piso} {depto}')
    elif piso:
        variantes.add(f'{dir_} {piso}')
        variantes.add(f'{dir_}{piso}')
    elif depto:
        variantes.add(f'{dir_} {depto}')
    # Primera palabra de la calle (ej. MORENO) suele colgarse al final.
    primera = dir_.split()[0] if dir_.split() else ''
    if primera and len(primera) >= 4:
        variantes.add(primera)
    return [v for v in variantes if v]


def _limpiar_descripcion_libro(desc, prop=None):
    """Sin ID de concepto, sin dirección del depto; una línea limpia."""
    import re
    import unicodedata

    t = (desc or '').strip()
    if not t:
        return ''
    t = _quitar_id_concepto_de_texto(t)
    # Quitar segmentos "— dirección…" al final (y repetidos).
    for marca in sorted(_variantes_direccion_propiedad_libro(prop), key=len, reverse=True):
        if not marca:
            continue
        esc = re.escape(marca)
        t = re.sub(
            rf'\s*[—–\-]\s*{esc}\s*$',
            '',
            t,
            flags=re.IGNORECASE,
        )
        t = re.sub(
            rf'\s+[—–\-]\s*{esc}\b',
            '',
            t,
            flags=re.IGNORECASE,
        )
        # También si quedó pegada sin guión al final.
        t = re.sub(rf'\s+{esc}\s*$', '', t, flags=re.IGNORECASE)

    t = re.sub(r'\s+', ' ', t).strip(' —–-')
    # Normalizar espacios raros
    t = ''.join(
        c for c in unicodedata.normalize('NFKC', t)
        if c == ' ' or not c.isspace()
    )
    return t.strip(' —–-')


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

    prop = getattr(mov, 'propiedad', None)

    if items:
        cuerpo = _formatear_items_concepto_libro(items)
        if prefijo_contrato and cuerpo:
            desc = f'{prefijo_contrato} — {cuerpo}'
        elif prefijo_contrato:
            desc = prefijo_contrato
        else:
            desc = cuerpo or f'Movimiento #{mov.id}'
        return _limpiar_descripcion_libro(desc, prop)

    # 3) Sin JSON: si el "resto" sigue siendo basura tipo [{...}], limpiar.
    if resto.lstrip().startswith(('[', '{')):
        return prefijo_contrato or f'Movimiento #{mov.id}'

    if prefijo_contrato and resto:
        desc = f'{prefijo_contrato} — {resto}'
    else:
        desc = txt or prefijo_contrato or f'Movimiento #{mov.id}'

    # No agregar la dirección del depto: ya está en el título del libro.
    return _limpiar_descripcion_libro(desc, prop)


def _monto_gasto_libro_sin_inquilino(mov, ars_total):
    """
    Parte del egreso que carga el depto / propietario en el libro.
    La parte a inquilino (proporcional) no suma: no es gasto del depto.
    """
    ars_total = Decimal(str(ars_total or 0))
    m_inq = Decimal(str(getattr(mov, 'monto_a_inquilino', None) or 0))
    m_prop = Decimal(str(getattr(mov, 'monto_a_propietario', None) or 0))
    m_of = Decimal(str(getattr(mov, 'monto_a_oficina', None) or 0))
    a_desc = (getattr(mov, 'a_descontar', None) or '').strip().lower()

    propio = (m_prop + m_of).quantize(Decimal('0.01'))
    if propio > 0:
        return propio
    if m_inq > 0 and ars_total > m_inq:
        return (ars_total - m_inq).quantize(Decimal('0.01'))
    if a_desc == 'inquilino' or (m_inq > 0 and ars_total > 0 and m_inq >= ars_total):
        return Decimal('0')
    return ars_total.quantize(Decimal('0.01')) if ars_total > 0 else Decimal('0')


def _fila_libro_desde_movimiento(mov, monto_prop_por_reserva=None, cotiz_por_reserva=None):
    """
    Mapea un MovimientoCaja a las columnas del libro.
    Ingresos de Operación N / Contrato #N no entran acá: van al libro recién
    con liquidación confirmada (monto del depto/propietario).
    En egresos solo la parte depto/propietario (excluye proporcional inquilino).
    Devuelve None si el egreso es 100% a cargo del inquilino (no va al libro).
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

    conc_chk = getattr(mov, 'concepto', None) or ''
    if _concepto_es_operacion_anulada(conc_chk):
        return None

    # Cobros de operación/contrato: no listar el bruto de caja.
    # El libro usa liquidaciones confirmadas (_filas_liquidaciones_confirmadas_libro).
    if not es_egreso:
        if re.search(r'Contrato\s*#?\s*\d+', conc_chk, re.IGNORECASE):
            return None
        if re.search(r'Operaci[oó]n\s*#?\s*\d+', conc_chk, re.IGNORECASE):
            return None

    # Egresos de pago de liquidación al propietario: el alquiler ya se acredita
    # por la fila de liquidación confirmada; no duplicar como gasto.
    if es_egreso:
        conc_eg = (getattr(mov, 'concepto', None) or '')
        if re.search(r'Liquidaci[oó]n\s+Propietario', conc_eg, re.IGNORECASE):
            return None

    if es_egreso:
        ars_bruto = ars
        ars = _monto_gasto_libro_sin_inquilino(mov, ars_bruto)
        if ars <= 0:
            return None
        if ars_bruto > 0 and ars < ars_bruto and usd > 0:
            usd = (usd * ars / ars_bruto).quantize(Decimal('0.01'))

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
        'clasificacion_libro': (getattr(mov, 'clasificacion_libro', None) or '').strip(),
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
    """get_or_create de costos compra/venta (valores USD del depto)."""
    costos, _ = CostosCompraLibroPropiedad.objects.get_or_create(
        propiedad=propiedad,
        defaults={
            'valor_depto_comprado': Decimal('0'),
            'gastos_escritura': Decimal('0'),
            'honorarios_pagados': Decimal('0'),
            'valor_depto_vendido': Decimal('0'),
            'gastos_escritura_venta': Decimal('0'),
            'honorarios_venta': Decimal('0'),
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
        'clasificacion_libro': '',
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
        'clasificacion_libro': (getattr(fila, 'clasificacion_libro', None) or '').strip(),
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
    orden = (request.GET.get('orden') or 'direccion').strip().lower()
    if orden not in ('direccion', 'piso', 'propietario'):
        orden = 'direccion'
    q = (request.GET.get('q') or '').strip()
    propiedades = _ordenar_propiedades_oficina(
        _filtrar_propiedades_oficina(_qs_propiedades_oficina(sucursal), q),
        orden=orden,
    )
    return render(
        request,
        'inmobiliaria/oficina/propiedades_lista.html',
        {
            'propiedades': propiedades,
            'total': len(propiedades),
            'orden': orden,
            'q': q,
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
    clasif_filtro = (request.GET.get('clasif') or 'todo').strip().lower()
    if clasif_filtro not in ('todo', 'facturado', 'negro'):
        clasif_filtro = 'todo'
    dr_desde = _parse_fecha(fecha_desde_s)
    dr_hasta = _parse_fecha(fecha_hasta_s)
    if dr_desde and dr_hasta and dr_hasta < dr_desde:
        dr_desde, dr_hasta = dr_hasta, dr_desde
        fecha_desde_s, fecha_hasta_s = dr_desde.isoformat(), dr_hasta.isoformat()

    inicio = _obtener_inicio_caja_libro(propiedad)
    costos = _obtener_costos_compra_libro(propiedad)

    # Corte duro: el libro de oficina arranca en la fecha de inicio de caja
    # de ese depto (nada anterior, ni ingresos ni gastos).
    fecha_corte = getattr(inicio, 'fecha', None)
    if fecha_corte and (dr_desde is None or dr_desde < fecha_corte):
        dr_desde = fecha_corte
        fecha_desde_s = fecha_corte.isoformat()

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
        f
        for f in (
            _fila_libro_desde_movimiento(
                m,
                monto_prop_por_reserva=monto_prop_por_reserva,
                cotiz_por_reserva=cotiz_por_reserva,
            )
            for m in movimientos
        )
        if f is not None
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
    filas.extend(
        _filas_liquidaciones_oficina_libro(
            propiedad,
            sucursal,
            movimientos=movimientos,
            dr_desde=dr_desde,
            dr_hasta=dr_hasta,
        )
    )

    # Anotaciones manuales (incluye importación Excel facturado).
    qs_manual = FilaManualLibroPropiedad.objects.filter(propiedad=propiedad)
    if dr_desde:
        qs_manual = qs_manual.filter(fecha__gte=dr_desde)
    if dr_hasta:
        qs_manual = qs_manual.filter(fecha__lte=dr_hasta)
    filas.extend(_fila_desde_manual(fm) for fm in qs_manual.order_by('fecha', 'id'))

    # Seguridad: descartar cualquier fila con fecha anterior al inicio de caja.
    if fecha_corte:
        def _fecha_sola(fila):
            fe = fila.get('fecha')
            if not fe:
                return None
            if isinstance(fe, datetime):
                try:
                    if timezone.is_aware(fe):
                        return timezone.localtime(fe).date()
                except Exception:
                    pass
                return fe.date()
            if isinstance(fe, date):
                return fe
            if hasattr(fe, 'date'):
                return fe.date()
            return None

        filas = [
            f for f in filas
            if (d := _fecha_sola(f)) is None or d >= fecha_corte
        ]
    else:
        def _fecha_sola(fila):
            fe = fila.get('fecha')
            if not fe:
                return None
            if isinstance(fe, datetime):
                try:
                    if timezone.is_aware(fe):
                        return timezone.localtime(fe).date()
                except Exception:
                    pass
                return fe.date()
            if isinstance(fe, date):
                return fe
            if hasattr(fe, 'date'):
                return fe.date()
            return None

    def _orden_fila(f):
        return (
            f.get('fecha') or timezone.now(),
            0 if f.get('es_inicio_caja') else 1,
            f.get('movimiento_id') or f.get('fila_manual_id') or 0,
        )

    # Importados (facturado + en negro) mezclados por fecha; luego totales; luego el resto.
    filas_import = [
        f for f in filas
        if f.get('es_manual')
        and (f.get('clasificacion_libro') or '') in ('facturado', 'negro')
    ]
    filas_resto = [
        f for f in filas
        if not (
            f.get('es_manual')
            and (f.get('clasificacion_libro') or '') in ('facturado', 'negro')
        )
    ]

    exige_clasif = bool(getattr(propiedad, 'libro_exige_facturado_negro', False))
    if exige_clasif and clasif_filtro in ('facturado', 'negro'):
        filas_import = [
            f for f in filas_import
            if (f.get('clasificacion_libro') or '') == clasif_filtro
        ]
        filas_resto = [
            f for f in filas_resto
            if (f.get('clasificacion_libro') or '') == clasif_filtro
        ]

    # Mezcla cronológica; ante misma fecha, facturado antes que en negro.
    def _orden_import(f):
        clas = (f.get('clasificacion_libro') or '')
        return (
            f.get('fecha') or timezone.now(),
            0 if clas == 'facturado' else 1 if clas == 'negro' else 2,
            f.get('fila_manual_id') or 0,
        )

    filas_import.sort(key=_orden_import)
    filas_resto.sort(key=_orden_fila)

    filas = [_fila_inicio_caja_libro(inicio)]
    filas.extend(filas_import)

    if filas_import:
        tot_imp = {
            'gastos_ars': sum((f['gastos_ars'] for f in filas_import), Decimal('0')),
            'alquileres_ars': sum((f['alquileres_ars'] for f in filas_import), Decimal('0')),
            'gastos_usd': sum((f['gastos_usd'] for f in filas_import), Decimal('0')),
            'ingreso_usd': sum((f['ingreso_usd'] for f in filas_import), Decimal('0')),
        }
        n_fact = sum(1 for f in filas_import if f.get('clasificacion_libro') == 'facturado')
        n_negro = sum(1 for f in filas_import if f.get('clasificacion_libro') == 'negro')
        etiqueta = 'TOTALES HASTA LA FECHA (importados'
        if clasif_filtro == 'facturado':
            etiqueta = 'TOTALES HASTA LA FECHA (gastos facturados importados)'
        elif clasif_filtro == 'negro':
            etiqueta = 'TOTALES HASTA LA FECHA (gastos en negro / no facturados)'
        else:
            etiqueta = (
                f'TOTALES HASTA LA FECHA (importados: {n_fact} facturados + '
                f'{n_negro} en negro)'
            )
        filas.append({
            'fecha': filas_import[-1].get('fecha'),
            'descripcion': etiqueta,
            'gastos_ars': tot_imp['gastos_ars'],
            'alquileres_ars': tot_imp['alquileres_ars'],
            'gastos_usd': tot_imp['gastos_usd'],
            'ingreso_usd': tot_imp['ingreso_usd'],
            'tipo_cambio': None,
            'movimiento_id': None,
            'tipo': 'SUBTOTAL',
            'sin_caja': False,
            'es_inicio_caja': False,
            'es_manual': False,
            'es_subtotal_hasta_fecha': True,
            'fila_manual_id': None,
            'clasificacion_libro': '',
        })

    filas.extend(filas_resto)

    totales = {
        'gastos_ars': sum(
            (f['gastos_ars'] for f in filas if not f.get('es_subtotal_hasta_fecha')),
            Decimal('0'),
        ),
        'alquileres_ars': sum(
            (f['alquileres_ars'] for f in filas if not f.get('es_subtotal_hasta_fecha')),
            Decimal('0'),
        ),
        'gastos_usd': sum(
            (f['gastos_usd'] for f in filas if not f.get('es_subtotal_hasta_fecha')),
            Decimal('0'),
        ),
        'ingreso_usd': sum(
            (f['ingreso_usd'] for f in filas if not f.get('es_subtotal_hasta_fecha')),
            Decimal('0'),
        ),
    }
    totales['balance_ars'] = totales['alquileres_ars'] - totales['gastos_ars']
    totales['balance_usd'] = totales['ingreso_usd'] - totales['gastos_usd']

    valor_vendido = Decimal(str(getattr(costos, 'valor_depto_vendido', 0) or 0))
    honorarios_venta = Decimal(str(getattr(costos, 'honorarios_venta', 0) or 0))
    escritura_venta = Decimal(str(getattr(costos, 'gastos_escritura_venta', 0) or 0))
    # Primero se suman todos los ingresos; después todos los gastos; TOTAL = ingresos − gastos.
    total_ingresos = valor_vendido + totales['ingreso_usd']
    total_gastos = (
        costos.valor_depto_comprado
        + costos.gastos_escritura
        + costos.honorarios_pagados
        + escritura_venta
        + honorarios_venta
        + totales['gastos_usd']
    )
    resumen = {
        'valor_depto_comprado': costos.valor_depto_comprado,
        'gastos_escritura': costos.gastos_escritura,
        'honorarios_pagados': costos.honorarios_pagados,
        'valor_depto_vendido': valor_vendido,
        'gastos_escritura_venta': escritura_venta,
        'honorarios_venta': honorarios_venta,
        'gastos_usd': totales['gastos_usd'],
        'ingreso_usd': totales['ingreso_usd'],
        'total_ingresos': total_ingresos,
        'total_gastos': total_gastos,
        'total': total_ingresos - total_gastos,
    }

    otras = _ordenar_propiedades_oficina(
        _qs_propiedades_oficina(sucursal, request.user),
        orden='piso',
    )

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
            'clasif_filtro': clasif_filtro,
            'exige_facturado_negro': exige_clasif,
            'inicio_caja': inicio,
            'total_usd_inicio': (
                Decimal(str(inicio.ingreso_usd or 0))
                - Decimal(str(inicio.gastos_usd or 0))
            ),
        },
    )


@login_required
@require_POST
def oficina_propiedad_libro_importar_facturado(request, propiedad_id):
    """Importa el Excel de gastos de Gery 1759 como filas «facturado»."""
    return _oficina_propiedad_libro_importar_excel(
        request, propiedad_id, clasificacion='facturado'
    )


@login_required
@require_POST
def oficina_propiedad_libro_importar_negro(request, propiedad_id):
    """Importa el Excel de gastos de Gery 1759 como filas «en negro» / no facturado."""
    return _oficina_propiedad_libro_importar_excel(
        request, propiedad_id, clasificacion='negro'
    )


def _oficina_propiedad_libro_importar_excel(request, propiedad_id, clasificacion):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    from inmobiliaria.models import Propiedad
    from inmobiliaria.gery_1759_facturado_import import importar_gery_1759_excel

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return HttpResponseForbidden()

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    if not getattr(propiedad, 'libro_exige_facturado_negro', False):
        messages.error(request, 'Esta propiedad no usa clasificación facturado / en negro.')
        return redirect('inmobiliaria:oficina_propiedad_libro', propiedad_id=propiedad_id)

    try:
        result = importar_gery_1759_excel(
            propiedad=propiedad,
            clasificacion=clasificacion,
            force=False,
        )
    except Exception as exc:
        logger.exception('Error importando Excel %s de %s', clasificacion, propiedad_id)
        messages.error(request, f'Error al importar: {exc}')
        return redirect('inmobiliaria:oficina_propiedad_libro', propiedad_id=propiedad_id)

    if result['ok']:
        messages.success(request, result['mensaje'])
        fecha_ini = result.get('fecha_inicio_caja')
        # Siempre abrir en «Todo junto» para ver facturado y en negro mezclados.
        if fecha_ini:
            return redirect(
                f"{reverse('inmobiliaria:oficina_propiedad_libro', args=[propiedad_id])}"
                f"?fecha_desde={fecha_ini}&clasif=todo"
            )
        return redirect(
            f"{reverse('inmobiliaria:oficina_propiedad_libro', args=[propiedad_id])}"
            f"?clasif=todo"
        )

    messages.error(request, result['mensaje'])
    return redirect('inmobiliaria:oficina_propiedad_libro', propiedad_id=propiedad_id)


@login_required
@require_POST
def oficina_propiedad_libro_clasificacion(request, propiedad_id):
    """Actualiza Facturado / En negro de una fila del libro."""
    if not _puede_oficina(request.user):
        return JsonResponse({'ok': False, 'error': 'Sin permiso.'}, status=403)

    from inmobiliaria.models import LiquidacionPropietario, Propiedad
    from inmobiliaria.models.caja import MovimientoCaja

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return JsonResponse({'ok': False, 'error': 'Sin permiso sobre esa propiedad.'}, status=403)

    propiedad = get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    if not getattr(propiedad, 'libro_exige_facturado_negro', False):
        return JsonResponse(
            {'ok': False, 'error': 'Esta propiedad no usa clasificación facturado/negro.'},
            status=400,
        )

    clasif = (request.POST.get('clasificacion_libro') or '').strip().lower()
    if clasif not in ('facturado', 'negro', ''):
        return JsonResponse({'ok': False, 'error': 'Clasificación inválida.'}, status=400)

    mov_id = (request.POST.get('movimiento_id') or '').strip()
    liq_id = (request.POST.get('liquidacion_id') or '').strip()
    fila_id = (request.POST.get('fila_manual_id') or '').strip()

    if mov_id.isdigit():
        mov = MovimientoCaja.objects.filter(
            pk=int(mov_id),
            propiedad_id=propiedad_id,
            sucursal=sucursal,
            fecha_eliminacion__isnull=True,
        ).first()
        if not mov:
            return JsonResponse({'ok': False, 'error': 'Movimiento no encontrado.'}, status=404)
        mov.clasificacion_libro = clasif
        mov.save(update_fields=['clasificacion_libro'])
        return JsonResponse({'ok': True, 'clasificacion_libro': clasif})

    if liq_id.isdigit():
        liq = LiquidacionPropietario.objects.filter(
            pk=int(liq_id),
            propiedad_id=propiedad_id,
            sucursal=sucursal,
        ).first()
        if not liq:
            return JsonResponse({'ok': False, 'error': 'Liquidación no encontrada.'}, status=404)
        liq.clasificacion_libro = clasif
        liq.save(update_fields=['clasificacion_libro'])
        return JsonResponse({'ok': True, 'clasificacion_libro': clasif})

    if fila_id.isdigit():
        fila = FilaManualLibroPropiedad.objects.filter(
            pk=int(fila_id),
            propiedad_id=propiedad_id,
        ).first()
        if not fila:
            return JsonResponse({'ok': False, 'error': 'Fila no encontrada.'}, status=404)
        fila.clasificacion_libro = clasif
        fila.save(update_fields=['clasificacion_libro'])
        return JsonResponse({'ok': True, 'clasificacion_libro': clasif})

    return JsonResponse({'ok': False, 'error': 'Indicá la fila a clasificar.'}, status=400)


@login_required
def oficina_propiedad_libro_liquidacion_modal(request, propiedad_id, liquidacion_id):
    """HTML del resumen de liquidación para el modal del libro."""
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    from inmobiliaria.liquidacion_operacion import info_operacion_liquidacion
    from inmobiliaria.models import Propiedad
    from inmobiliaria.views import (
        _context_liquidacion_cobranzas,
        _observaciones_visibles_gasto,
        _periodo_liquidado_display,
    )

    sucursal, en_cartera = _propiedad_en_cartera_oficina(request.user, propiedad_id)
    if not en_cartera:
        return HttpResponseForbidden()

    get_object_or_404(Propiedad, pk=propiedad_id, sucursal=sucursal)
    liquidacion = get_object_or_404(
        LiquidacionPropietario.objects.select_related(
            'propietario',
            'propiedad',
            'reserva',
            'contrato',
            'movimiento_caja',
            'sucursal',
        ).prefetch_related('gastos'),
        pk=liquidacion_id,
        propiedad_id=propiedad_id,
        sucursal=sucursal,
    )
    try:
        liquidacion._recalcular_monto_a_pagar_fields()
    except Exception:
        pass

    pd, ph = _periodo_liquidado_display(liquidacion)
    liquidacion.periodo_desde_display = pd
    liquidacion.periodo_hasta_display = ph

    gastos_list = list(liquidacion.gastos.all().order_by('-fecha_creacion'))
    for g in gastos_list:
        g.detalle_visible = _observaciones_visibles_gasto(g)

    ctx = {
        'liquidacion': liquidacion,
        'info_operacion_liquidacion': info_operacion_liquidacion(liquidacion),
        'gastos': gastos_list,
        **_context_liquidacion_cobranzas(liquidacion, request),
    }
    return render(
        request,
        'inmobiliaria/oficina/_libro_liquidacion_modal.html',
        ctx,
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
        gastos_usd = parse_decimal_monto(request.POST.get('gastos_usd', '0'))
        ingreso_usd = parse_decimal_monto(request.POST.get('ingreso_usd', '0'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Monto inválido.'}, status=400)

    # Compatibilidad: si mandan los campos viejos monto_ars / monto_usd
    if (
        abs(gastos_usd) <= 0
        and abs(ingreso_usd) <= 0
        and (request.POST.get('monto_ars') or request.POST.get('monto_usd'))
    ):
        try:
            monto_usd = parse_decimal_monto(request.POST.get('monto_usd', '0'))
        except Exception:
            monto_usd = Decimal('0')
        if monto_usd >= 0:
            ingreso_usd = monto_usd
        else:
            gastos_usd = abs(monto_usd)

    inicio.fecha = fecha
    # ARS y tipo de cambio ya no se editan en el formulario de inicio
    inicio.gastos_ars = Decimal('0')
    inicio.alquileres_ars = Decimal('0')
    inicio.gastos_usd = gastos_usd.quantize(Decimal('0.01'))
    inicio.ingreso_usd = ingreso_usd.quantize(Decimal('0.01'))
    inicio.tipo_cambio = None
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
    """Guarda costos de compra/venta USD y observaciones de este depto."""
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
        valor_vendido = parse_decimal_monto(request.POST.get('valor_depto_vendido', '0'))
        escritura_venta = parse_decimal_monto(request.POST.get('gastos_escritura_venta', '0'))
        honorarios_venta = parse_decimal_monto(request.POST.get('honorarios_venta', '0'))
    except Exception:
        return JsonResponse({'ok': False, 'error': 'Monto inválido.'}, status=400)

    observaciones = (request.POST.get('observaciones') or '').strip()
    if len(observaciones) > 2000:
        observaciones = observaciones[:2000]
    escribania = (request.POST.get('escribania') or '').strip()
    if len(escribania) > 255:
        escribania = escribania[:255]

    costos.valor_depto_comprado = valor.quantize(Decimal('0.01'))
    costos.gastos_escritura = escritura.quantize(Decimal('0.01'))
    costos.honorarios_pagados = honorarios.quantize(Decimal('0.01'))
    costos.valor_depto_vendido = valor_vendido.quantize(Decimal('0.01'))
    costos.gastos_escritura_venta = escritura_venta.quantize(Decimal('0.01'))
    costos.honorarios_venta = honorarios_venta.quantize(Decimal('0.01'))
    costos.escribania = escribania
    costos.observaciones = observaciones
    costos.actualizado_por = request.user
    costos.save()

    return JsonResponse(
        {
            'ok': True,
            'valor_depto_comprado': format_monto_argentino(costos.valor_depto_comprado),
            'gastos_escritura': format_monto_argentino(costos.gastos_escritura),
            'honorarios_pagados': format_monto_argentino(costos.honorarios_pagados),
            'valor_depto_vendido': format_monto_argentino(costos.valor_depto_vendido),
            'gastos_escritura_venta': format_monto_argentino(costos.gastos_escritura_venta),
            'honorarios_venta': format_monto_argentino(costos.honorarios_venta),
            'escribania': costos.escribania,
            'observaciones': costos.observaciones,
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
    Completa cotización USD en un movimiento de caja, una liquidación del libro
    o una operación (fila «op.»): calcula Ingreso/Gastos en dólar.
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

    # --- Liquidación del libro (fila «op.» con liquidacion_id) ---
    liquidacion_id = (request.POST.get('liquidacion_id') or '').strip()
    if liquidacion_id.isdigit():
        liq = LiquidacionPropietario.objects.filter(
            pk=int(liquidacion_id),
            propiedad=propiedad,
            sucursal=sucursal,
            estado__in=_ESTADOS_LIQUIDACION_LIBRO,
        ).select_related('reserva').first()
        if not liq:
            return JsonResponse({'ok': False, 'error': 'Liquidación no encontrada.'}, status=404)

        liq.cotizacion_dolar = cotiz
        liq.save(update_fields=['cotizacion_dolar'])

        rid = getattr(liq, 'reserva_id', None)
        if rid:
            CotizacionLibroOperacion.objects.update_or_create(
                reserva_id=rid,
                defaults={
                    'cotizacion_dolar': cotiz,
                    'actualizado_por': request.user,
                },
            )

        moneda = (getattr(liq, 'moneda', None) or 'ARS').strip().upper()
        monto = Decimal(str(getattr(liq, 'monto_propietario', None) or 0))
        if monto <= 0:
            monto = Decimal(str(getattr(liq, 'monto_a_pagar', None) or 0))
        gastos_usd = Decimal('0')
        ingreso_usd = Decimal('0')
        alquileres_ars = Decimal('0')
        if moneda == 'USD':
            ingreso_usd = monto
            alquileres_ars = (monto * cotiz).quantize(Decimal('0.01'))
        else:
            alquileres_ars = monto
            ingreso_usd = (monto / cotiz).quantize(Decimal('0.01')) if monto > 0 else Decimal('0')

        return JsonResponse({
            'ok': True,
            'liquidacion_id': liq.id,
            'reserva_id': rid,
            'gastos_usd': _fmt(gastos_usd),
            'ingreso_usd': _fmt(ingreso_usd),
            'alquileres_ars': _fmt(alquileres_ars),
            'tipo_cambio': _fmt(cotiz),
            'tipo': 'IN',
            'message': 'Cotización de la liquidación guardada.',
        })

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
    if not fila:
        return JsonResponse({
            'ok': True,
            'movimiento_id': movimiento.id,
            'gastos_usd': _fmt(Decimal('0')),
            'ingreso_usd': _fmt(Decimal('0')),
            'tipo_cambio': _fmt(cotiz),
            'tipo': 'EG',
            'message': 'Cotización guardada.',
        })
    return JsonResponse({
        'ok': True,
        'movimiento_id': movimiento.id,
        'gastos_usd': _fmt(fila['gastos_usd']),
        'ingreso_usd': _fmt(fila['ingreso_usd']),
        'tipo_cambio': _fmt(fila['tipo_cambio']),
        'tipo': fila['tipo'],
        'message': 'Cotización guardada.',
    })


# ---------------------------------------------------------------------------
# Personas de oficina (beneficiarios de vales que no son productores)
# ---------------------------------------------------------------------------

@login_required
def oficina_personas(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')

    personas = (
        PersonaOficina.objects.filter(sucursal=sucursal)
        .annotate(num_vales=Count('vales'))
        .order_by('-activa', 'apellido', 'nombre', 'id')
    )
    return render(
        request,
        'inmobiliaria/oficina/personas.html',
        {'personas': personas},
    )


@login_required
@require_POST
def oficina_persona_crear(request):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    if not sucursal:
        return HttpResponseForbidden('Tu usuario no tiene sucursal asignada.')

    apellido = (request.POST.get('apellido') or '').strip()
    nombre = (request.POST.get('nombre') or '').strip()
    dni = (request.POST.get('dni') or '').strip()
    notas = (request.POST.get('notas') or '').strip()

    if not apellido and not nombre:
        messages.error(request, 'Indicá apellido o nombre.')
        return redirect('inmobiliaria:oficina_personas')

    persona = PersonaOficina.objects.create(
        sucursal=sucursal,
        apellido=apellido,
        nombre=nombre,
        dni=dni,
        notas=notas,
        activa=True,
    )
    messages.success(request, f'Persona guardada: {persona.nombre_completo()}.')
    return redirect('inmobiliaria:oficina_personas')


@login_required
@require_POST
def oficina_persona_editar(request, persona_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    persona = get_object_or_404(PersonaOficina, id=persona_id, sucursal=sucursal)

    apellido = (request.POST.get('apellido') or '').strip()
    nombre = (request.POST.get('nombre') or '').strip()
    dni = (request.POST.get('dni') or '').strip()
    notas = (request.POST.get('notas') or '').strip()

    if not apellido and not nombre:
        messages.error(request, 'Indicá apellido o nombre.')
        return redirect('inmobiliaria:oficina_personas')

    persona.apellido = apellido
    persona.nombre = nombre
    persona.dni = dni
    persona.notas = notas
    persona.save(update_fields=['apellido', 'nombre', 'dni', 'notas'])

    # Mantener nombres legibles en vales ya vinculados
    ValeVendedor.objects.filter(persona_oficina=persona).update(
        beneficiario_apellido=apellido,
        beneficiario_nombre=nombre,
        beneficiario_dni=dni,
    )
    messages.success(request, f'Persona actualizada: {persona.nombre_completo()}.')
    return redirect('inmobiliaria:oficina_personas')


@login_required
@require_POST
def oficina_persona_toggle(request, persona_id):
    if not _puede_oficina(request.user):
        return HttpResponseForbidden()

    sucursal = request.user.sucursal
    persona = get_object_or_404(PersonaOficina, id=persona_id, sucursal=sucursal)
    persona.activa = not persona.activa
    persona.save(update_fields=['activa'])
    estado = 'activada' if persona.activa else 'desactivada'
    messages.success(request, f'Persona {estado}: {persona.nombre_completo()}.')
    return redirect('inmobiliaria:oficina_personas')
