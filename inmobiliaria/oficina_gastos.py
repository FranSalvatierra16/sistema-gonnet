"""Helpers compartidos para gastos de oficina (panel y movimientos de caja)."""
from decimal import Decimal

from django.utils import timezone

from inmobiliaria.models import CategoriaGastoOficina, GastoOficina, Vendedor

CATEGORIAS_INICIALES = [
    ('Sueldos', ['Administración', 'Productores', 'Cargas sociales']),
    ('Gastos contables', ['Honorarios contador', 'Cargas sociales', 'Impuestos']),
    ('Servicios', ['Luz', 'Internet', 'Teléfono', 'Limpieza']),
    ('Inmueble oficina', ['Alquiler', 'Expensas', 'Mantenimiento']),
]


def asegurar_categorias_base(sucursal):
    if CategoriaGastoOficina.objects.filter(sucursal=sucursal).exists():
        return False
    orden = 0
    for raiz, hijos in CATEGORIAS_INICIALES:
        parent = CategoriaGastoOficina.objects.create(
            sucursal=sucursal,
            nombre=raiz,
            orden=orden,
        )
        orden += 1
        for i, hijo in enumerate(hijos):
            CategoriaGastoOficina.objects.create(
                sucursal=sucursal,
                parent=parent,
                nombre=hijo,
                orden=i,
            )
    return True


def categorias_opciones(sucursal):
    """Lista plana para selects: solo hojas (subcategorías) o raíces sin hijos."""
    raices = (
        CategoriaGastoOficina.objects.filter(sucursal=sucursal, activa=True, parent__isnull=True)
        .prefetch_related('subcategorias')
        .order_by('orden', 'nombre')
    )
    opciones = []
    for raiz in raices:
        hijos = [s for s in raiz.subcategorias.all() if s.activa]
        if hijos:
            for hijo in sorted(hijos, key=lambda x: (x.orden, x.nombre)):
                opciones.append({'id': hijo.id, 'label': hijo.nombre_ruta()})
        else:
            opciones.append({'id': raiz.id, 'label': raiz.nombre})
    return opciones


def categoria_gasto_requiere_productor(categoria):
    """Sueldos › Productores exige elegir vendedor/productor."""
    if not categoria or not categoria.parent_id:
        return False
    parent = categoria.parent
    return (
        (parent.nombre or '').strip().lower() == 'sueldos'
        and (categoria.nombre or '').strip().lower() == 'productores'
    )


def categorias_opciones_con_flags(sucursal):
    opciones = categorias_opciones(sucursal)
    ids = [op['id'] for op in opciones]
    cats = {
        c.id: c
        for c in CategoriaGastoOficina.objects.filter(id__in=ids).select_related('parent')
    }
    for op in opciones:
        cat = cats.get(op['id'])
        op['requiere_productor'] = categoria_gasto_requiere_productor(cat)
    return opciones


def registrar_gasto_oficina_desde_movimiento(
    movimiento,
    categoria,
    descripcion,
    observaciones='',
    vendedor=None,
    usuario=None,
):
    total = (
        Decimal(str(movimiento.monto_efectivo or 0))
        + Decimal(str(movimiento.monto_cheque or 0))
        + Decimal(str(movimiento.monto_tarjeta or 0))
        + Decimal(str(movimiento.monto_deposito or 0))
    )
    fecha = timezone.localdate()
    if movimiento.fecha:
        fecha = timezone.localtime(movimiento.fecha).date()

    return GastoOficina.objects.create(
        sucursal=movimiento.sucursal,
        categoria=categoria,
        fecha=fecha,
        monto=total,
        descripcion=(descripcion or categoria.nombre_ruta())[:255],
        observaciones=observaciones or '',
        movimiento_caja=movimiento,
        vendedor=vendedor,
        usuario_creacion=usuario,
    )


def validar_gasto_oficina_post(sucursal, categoria_id, descripcion, vendedor_id_raw):
    """
    Valida datos de gasto de oficina desde nuevo movimiento.
    Retorna (categoria, vendedor, error_msg).
    """
    if not categoria_id.isdigit():
        return None, None, 'Elegí la categoría del gasto de oficina.'

    categoria = CategoriaGastoOficina.objects.filter(
        id=int(categoria_id),
        sucursal=sucursal,
        activa=True,
    ).select_related('parent').first()
    if not categoria:
        return None, None, 'La categoría de gasto de oficina no es válida.'

    descripcion = (descripcion or '').strip()
    if not descripcion:
        return None, None, 'La descripción del gasto de oficina es obligatoria.'

    vendedor = None
    if categoria_gasto_requiere_productor(categoria):
        if not vendedor_id_raw:
            return None, None, 'Para Sueldos › Productores tenés que elegir el productor.'
        try:
            vid = int(vendedor_id_raw)
        except (TypeError, ValueError):
            return None, None, 'ID de productor inválido.'
        vendedor = Vendedor.objects.filter(id=vid, sucursal=sucursal).first()
        if not vendedor:
            return None, None, 'El productor elegido no pertenece a esta sucursal.'

    return categoria, vendedor, None
