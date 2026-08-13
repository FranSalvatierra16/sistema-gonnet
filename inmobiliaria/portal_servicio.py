"""
Portal público (/web/): búsqueda por operación.
Reutiliza criterios del backoffice; no crea reservas.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from django.db.models import Prefetch, Q

from inmobiliaria.busqueda_propiedades_reserva import (
    calcular_precio_total_reserva_fechas,
    cargar_contexto_bulk_busqueda,
    contrato_solapa_rango,
    mapa_precios_propiedad,
    periodo_cubierto_por_disponibilidad_forzada,
    periodo_cubierto_por_disponibilidades,
    reservas_solapan_rango,
)
from inmobiliaria.models import ImagenPropiedad, Precio, Propiedad
from inmobiliaria.models.propiedad import ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD
from inmobiliaria.precio_temporada_reserva import rango_vacaciones_invierno_sucursal

# Solo este productor (Vendedor/user) ve y gestiona la página web en el backoffice.
PRODUCTOR_PORTAL_WEB_ID = 24

OPERACIONES_PORTAL = (
    ('alquiler_temporario', 'Alquiler temporario'),
    ('venta', 'Venta'),
    ('24_meses', '24 meses'),
    ('invierno', 'Invierno'),
)

OPERACION_LABELS = dict(OPERACIONES_PORTAL)
OPERACION_BADGES = {
    'alquiler_temporario': 'Alquiler',
    'venta': 'Venta',
    '24_meses': '24 meses',
    'invierno': 'Invierno',
}


def usuario_gestiona_portal_web(user) -> bool:
    """True si el usuario puede ver menús/acciones de portal web en el sistema."""
    return bool(user and getattr(user, 'is_authenticated', False) and user.id == PRODUCTOR_PORTAL_WEB_ID)


def parse_fecha_portal(s):
    if not s:
        return None
    st = str(s).strip()[:10]
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
        try:
            return datetime.strptime(st, fmt).date()
        except ValueError:
            continue
    return None


def normalizar_operacion(raw: str, default: str = 'alquiler_temporario') -> str:
    v = (raw or '').strip().lower().replace('-', '_')
    if not v:
        return default
    aliases = {
        'temporario': 'alquiler_temporario',
        'alquiler': 'alquiler_temporario',
        'alquiler_temporario': 'alquiler_temporario',
        'venta': 'venta',
        '24_meses': '24_meses',
        'meses_24': '24_meses',
        '24meses': '24_meses',
        'invierno': 'invierno',
    }
    return aliases.get(v, default if default else v)


def es_codigo_operacion(raw: str) -> bool:
    v = (raw or '').strip().lower().replace('-', '_')
    return v in {
        'temporario', 'alquiler', 'alquiler_temporario',
        'venta', '24_meses', 'meses_24', '24meses', 'invierno',
    }


def qs_propiedades_portal():
    """Propiedades publicadas en la web (todas las sucursales)."""
    return (
        Propiedad.objects.filter(publicar_web=True)
        .select_related('sucursal', 'info_venta', 'info_meses', 'info_invierno')
        .prefetch_related(
            Prefetch(
                'imagenes',
                queryset=ImagenPropiedad.objects.order_by('orden', 'id'),
                to_attr='fotos_ordenadas',
            ),
            Prefetch('precios', queryset=Precio.objects.all(), to_attr='todos_precios'),
        )
    )


def qs_destacadas_portal(limit=12):
    return qs_propiedades_portal().filter(destacada_web=True).order_by('id')[:limit]


def _vacaciones_invierno_sucursal(sucursal):
    return rango_vacaciones_invierno_sucursal(sucursal)


def _aplicar_filtros_atributos(
    qs,
    *,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
):
    if ficha:
        qs = qs.filter(id__icontains=str(ficha).strip())
    if ambientes:
        try:
            qs = qs.filter(ambientes=int(ambientes))
        except (TypeError, ValueError):
            pass
    if q:
        qq = str(q).strip()
        qs = qs.filter(
            Q(titulo__icontains=qq)
            | Q(direccion__icontains=qq)
            | Q(ubicacion__icontains=qq)
            | Q(descripcion__icontains=qq)
            | Q(id__icontains=qq)
        )
    if tipo_inmueble:
        qs = qs.filter(tipo_inmueble=tipo_inmueble)
    if valoracion:
        qs = qs.filter(valoracion=valoracion)
    if vista:
        qs = qs.filter(vista=vista)

    comodidades = comodidades or []
    campos_bool = {
        'cochera', 'parrilla', 'reciclado', 'terraza', 'baulera', 'seguridad',
        'vista_panoramica', 'patio', 'piscina', 'a_estrenar', 'balcon', 'lavadero',
        'vista_al_Mar', 'apto_credito', 'amoblado', 'wifi',
    }
    for c in comodidades:
        if c in campos_bool:
            qs = qs.filter(**{c: True})
    return qs


def _resultado_base(prop, *, precio_total=None, precio_label='', noches=None, operacion=''):
    fotos = list(getattr(prop, 'fotos_ordenadas', None) or [])[:8]
    return {
        'propiedad': prop,
        'precio_total': precio_total if precio_total is not None else Decimal('0'),
        'precio_label': precio_label,
        'noches': noches,
        'foto': fotos[0] if fotos else None,
        'fotos': fotos,
        'sucursal_nombre': getattr(getattr(prop, 'sucursal', None), 'nombre', '') or '',
        'operacion': operacion,
        'badge': OPERACION_BADGES.get(operacion, 'Alquiler'),
    }


def buscar_temporario_portal(
    *,
    fecha_inicio,
    fecha_fin,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
    limite=120,
):
    """Propiedades publicadas disponibles en el rango (misma lógica de ocupación del sistema)."""
    if not fecha_inicio or not fecha_fin or fecha_fin <= fecha_inicio:
        return []

    qs = _aplicar_filtros_atributos(
        qs_propiedades_portal(),
        ficha=ficha,
        ambientes=ambientes,
        q=q,
        tipo_inmueble=tipo_inmueble,
        valoracion=valoracion,
        vista=vista,
        comodidades=comodidades,
    )

    props = list(qs[:500])
    if not props:
        return []

    ids = [p.id for p in props]
    ctx = cargar_contexto_bulk_busqueda(ids, fecha_inicio, fecha_fin)
    resultados = []
    noches = (fecha_fin - fecha_inicio).days

    for prop in props:
        disp = ctx['disp_por_prop'].get(prop.id, [])
        cubierto, _, _ = periodo_cubierto_por_disponibilidades(disp, fecha_inicio, fecha_fin)
        forzado, _, _ = periodo_cubierto_por_disponibilidad_forzada(disp, fecha_inicio, fecha_fin)
        if not cubierto and not forzado:
            continue

        if contrato_solapa_rango(ctx['contratos_por_prop'].get(prop.id, []), fecha_inicio, fecha_fin):
            continue

        reservas = ctx['reservas_por_prop'].get(prop.id, [])
        bloquean = [
            r
            for r in reservas_solapan_rango(reservas, fecha_inicio, fecha_fin)
            if (r.estado in ESTADOS_RESERVA_OCUPAN_DISPONIBILIDAD)
            and not getattr(r, 'es_alquiler_sindicato', False)
        ]
        if bloquean and not forzado:
            continue

        precios_map = mapa_precios_propiedad(prop)
        vac = _vacaciones_invierno_sucursal(getattr(prop, 'sucursal', None))
        precio = calcular_precio_total_reserva_fechas(
            fecha_inicio, fecha_fin, precios_map, vacaciones_invierno=vac
        )
        resultados.append(
            _resultado_base(
                prop,
                precio_total=precio or Decimal('0'),
                noches=noches,
                operacion='alquiler_temporario',
            )
        )
        if len(resultados) >= limite:
            break

    resultados.sort(key=lambda r: (r['precio_total'] or Decimal('0'), r['propiedad'].id))
    return resultados


def buscar_venta_portal(
    *,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
    limite=200,
):
    """Mismo criterio que el listado interno de ventas + publicar_web."""
    qs = qs_propiedades_portal().filter(
        info_venta__en_venta=True,
        info_venta__estado__in=['disponible', 'reservado'],
    )
    qs = _aplicar_filtros_atributos(
        qs,
        ficha=ficha,
        ambientes=ambientes,
        q=q,
        tipo_inmueble=tipo_inmueble,
        valoracion=valoracion,
        vista=vista,
        comodidades=comodidades,
    ).order_by('info_venta__precio_venta', 'direccion')[:limite]

    resultados = []
    for prop in qs:
        info = getattr(prop, 'info_venta', None)
        precio = getattr(info, 'precio_venta', None) or Decimal('0')
        resultados.append(
            _resultado_base(
                prop,
                precio_total=precio,
                precio_label='',
                operacion='venta',
            )
        )
    return resultados


def buscar_24_meses_portal(
    *,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
    limite=200,
):
    """Mismo criterio que alquileres 24 meses internos (disponibles + ofrecibles) + publicar_web."""
    qs = qs_propiedades_portal().filter(info_meses__disponible=True).filter(
        Q(info_meses__estado='disponible')
        | Q(info_meses__ofrecible_desde__isnull=False)
    )
    qs = _aplicar_filtros_atributos(
        qs,
        ficha=ficha,
        ambientes=ambientes,
        q=q,
        tipo_inmueble=tipo_inmueble,
        valoracion=valoracion,
        vista=vista,
        comodidades=comodidades,
    ).order_by('info_meses__precio_mensual', 'direccion')[:limite]

    resultados = []
    for prop in qs:
        info = getattr(prop, 'info_meses', None)
        precio = getattr(info, 'precio_mensual', None) or Decimal('0')
        resultados.append(
            _resultado_base(
                prop,
                precio_total=precio,
                precio_label='/mes',
                operacion='24_meses',
            )
        )
    return resultados


def buscar_invierno_portal(
    *,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
    limite=200,
):
    """Mismo criterio que alquileres invierno internos (disponibles) + publicar_web."""
    qs = qs_propiedades_portal().filter(
        info_invierno__disponible=True,
        info_invierno__estado='disponible',
    )
    qs = _aplicar_filtros_atributos(
        qs,
        ficha=ficha,
        ambientes=ambientes,
        q=q,
        tipo_inmueble=tipo_inmueble,
        valoracion=valoracion,
        vista=vista,
        comodidades=comodidades,
    ).order_by('info_invierno__precio_mensual', 'direccion')[:limite]

    resultados = []
    for prop in qs:
        info = getattr(prop, 'info_invierno', None)
        precio = getattr(info, 'precio_mensual', None) or Decimal('0')
        resultados.append(
            _resultado_base(
                prop,
                precio_total=precio,
                precio_label='/mes',
                operacion='invierno',
            )
        )
    return resultados


def buscar_portal(
    *,
    operacion='alquiler_temporario',
    fecha_inicio=None,
    fecha_fin=None,
    ficha='',
    ambientes=None,
    q='',
    tipo_inmueble='',
    valoracion='',
    vista='',
    comodidades=None,
    limite=200,
):
    op = normalizar_operacion(operacion)
    kwargs = dict(
        ficha=ficha,
        ambientes=ambientes,
        q=q,
        tipo_inmueble=tipo_inmueble,
        valoracion=valoracion,
        vista=vista,
        comodidades=comodidades,
        limite=limite,
    )
    if op == 'venta':
        return buscar_venta_portal(**kwargs)
    if op == '24_meses':
        return buscar_24_meses_portal(**kwargs)
    if op == 'invierno':
        return buscar_invierno_portal(**kwargs)
    return buscar_temporario_portal(
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        **kwargs,
    )


def titulo_publico_propiedad(prop):
    t = (getattr(prop, 'titulo', None) or '').strip()
    if t:
        return t
    partes = [(prop.direccion or '').strip()]
    if getattr(prop, 'piso', None):
        partes.append(f'Piso {prop.piso}')
    if getattr(prop, 'departamento', None):
        partes.append(f'Dpto {prop.departamento}')
    return ' · '.join(p for p in partes if p) or f'Ficha {prop.id}'
