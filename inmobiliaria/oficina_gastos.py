"""Helpers compartidos para gastos de oficina (panel y movimientos de caja)."""
import unicodedata
from decimal import Decimal

from django.db import IntegrityError
from django.utils import timezone

from inmobiliaria.models import CategoriaGastoOficina, GastoOficina, Vendedor
from inmobiliaria.models.caja import TipoMovimientoCajaEnum

# Raíces cuyas subcategorías se sincronizan con los vendedores activos de la sucursal.
RAICES_SUBCATEGORIAS_VENDEDOR = ('Sueldos', 'Vales', 'Comisiones vendedores')

# Estructura del resumen de cierre mensual (modelo PDF).
ESTRUCTURA_CIERRE_OFICINA = [
    ('Sueldos', '__vendedores__'),
    (
        'Gastos generales',
        [
            '492-5353', '494-1212', '495-9696', '495-9697', '495-9846', '495-9484',
            'Abogado', 'Alarma Nikro', 'Antonio', 'ARBA', 'Bancos', 'Cocheras oficina',
            'Col. Mart. Matrícula', 'Combustible', 'Compra capital', 'Corporativos',
            'Dispenser agua', 'EDEA', 'Expensas oficina', 'Galpón (V. Montes)',
            'Imp. municipal', 'Internet', 'Librería - Fotocopias - Correo',
            'Local Moreno (luz-serv-imp)', 'Oficina (mantenimiento)',
            'Oficina Bs. As. (alq-exp-etc)', 'OSSE', 'Posnet', 'Quinta',
            'Seguro deptos', 'Sistema (David)', 'Viáticos (colectivo - taxi)',
        ],
    ),
    (
        'Autos',
        ['Amarok', 'BMW', 'Casilla', 'Ford F 100', 'Mercedes Benz', 'Vitara'],
    ),
    (
        'Publicidad',
        [
            'Hosting', 'Facebook', 'Llaveros Gonnet Propiedades', 'La Plaza Inmobiliaria',
            'Dominio gonnet.com.ar', 'Revista de Todo SA', 'Mar del Plata.com', 'Kloster',
        ],
    ),
    (
        'Mantenimiento deptos',
        [
            'Roturas, faltantes y reposiciones',
            'Art. limpieza',
            'Limpieza deptos (Marta)',
            'Limpieza deptos (2)',
            'Limpieza deptos (3)',
        ],
    ),
    ('Comisiones vendedores', '__vendedores__'),
    ('Vales', '__vendedores__'),
    (
        'Gastos contables e impuestos',
        [
            'Honorarios contador', 'Pago 931', 'Pago IIBB', 'Pago I.V.A.', 'Ganancias', 'SEC',
            'Seguro La Estrella', 'FAECYS', 'INACAP', 'Jubilación martilleros', 'I.A.M.',
            'TISH - PYP',
        ],
    ),
    (
        'Ingresos',
        [
            'Comisión por ventas', 'Tasación', '24 meses', 'Com. alq. temporarios',
            'Com. alq. año e invierno', 'Gastos bancarios', 'Honorarios gestión cob.',
            'Honorarios Marbella',
        ],
    ),
]

# Compatibilidad con instalaciones que aún no tienen la estructura de cierre.
CATEGORIAS_INICIALES = ESTRUCTURA_CIERRE_OFICINA

# Seed anterior (pre-PDF): raíces y subcategorías a desactivar.
RAICES_LEGACY_OFICINA = frozenset({
    'servicios',
    'inmueble oficina',
    'gastos contables',
})
SUBCATEGORIAS_LEGACY_SUELDOS = frozenset({
    'administración',
    'administracion',
    'productores',
    'cargas sociales',
})
SUBCATEGORIAS_LEGACY_VALES = frozenset({'productores'})


def _normalizar_nombre_sucursal(nombre):
    t = (nombre or '').strip().lower()
    t = ''.join(
        c for c in unicodedata.normalize('NFD', t) if unicodedata.category(c) != 'Mn'
    )
    return t


def get_sucursal_referencia_categorias_oficina():
    """Sucursal maestra de categorías de gasto de oficina (Corrientes)."""
    from inmobiliaria.models.sucursal import Sucursal

    return Sucursal.objects.filter(nombre__icontains='corrientes').order_by('pk').first()


def sucursal_espeja_categorias_oficina_desde_referencia(sucursal):
    """True si esta sucursal debe copiar el árbol de categorías desde Corrientes (ej. Colón)."""
    if not sucursal:
        return False
    ref = get_sucursal_referencia_categorias_oficina()
    if not ref or sucursal.pk == ref.pk:
        return False
    return 'colon' in _normalizar_nombre_sucursal(sucursal.nombre)


def _resolver_vendedor_espejo(sucursal_destino, vendedor_origen):
    """Empareja productor de Corrientes con el de la sucursal destino (apellido + nombre)."""
    if not vendedor_origen or not sucursal_destino:
        return None
    ap = (vendedor_origen.apellido or '').strip()
    nom = (vendedor_origen.nombre or '').strip()
    qs = Vendedor.objects.filter(sucursal=sucursal_destino, is_active=True)
    if ap:
        qs = qs.filter(apellido__iexact=ap)
    if nom:
        qs = qs.filter(nombre__iexact=nom)
    return qs.first()


def sincronizar_categorias_gasto_oficina_desde_referencia(sucursal_destino, sucursal_origen=None):
    """
    Copia categorías y subcategorías activas/inactivas de Corrientes a la sucursal destino.
    Las subcategorías por vendedor se vinculan al productor homónimo en destino, si existe.
    """
    sucursal_origen = sucursal_origen or get_sucursal_referencia_categorias_oficina()
    if not sucursal_origen or not sucursal_destino or sucursal_origen.pk == sucursal_destino.pk:
        return {'creadas': 0, 'actualizadas': 0, 'omitido': True}

    creadas = 0
    actualizadas = 0
    raices_origen = list(
        CategoriaGastoOficina.objects.filter(sucursal=sucursal_origen, parent__isnull=True)
        .prefetch_related('subcategorias__vendedor')
        .order_by('orden', 'nombre')
    )
    nombres_raiz_espejo = set()

    for raiz_o in raices_origen:
        nombre_raiz = (raiz_o.nombre or '').strip()
        if not nombre_raiz:
            continue
        nombres_raiz_espejo.add(nombre_raiz.lower())
        raiz_d, created = _get_or_create_raiz(sucursal_destino, nombre_raiz, raiz_o.orden)
        if created:
            creadas += 1
        upd_raiz = []
        if raiz_d.activa != raiz_o.activa:
            raiz_d.activa = raiz_o.activa
            upd_raiz.append('activa')
        if raiz_d.orden != raiz_o.orden:
            raiz_d.orden = raiz_o.orden
            upd_raiz.append('orden')
        if upd_raiz:
            raiz_d.save(update_fields=upd_raiz)
            if not created:
                actualizadas += 1

        hijos_vistos = set()
        for hijo_o in raiz_o.subcategorias.all().order_by('orden', 'nombre'):
            vendedor_d = None
            if hijo_o.vendedor_id:
                vendedor_d = _resolver_vendedor_espejo(sucursal_destino, hijo_o.vendedor)
            nombre_hijo = (hijo_o.nombre or '').strip()
            hijo_d, created_h = _get_or_create_hijo(
                sucursal_destino,
                raiz_d,
                nombre_hijo,
                hijo_o.orden,
                vendedor=vendedor_d,
            )
            hijos_vistos.add((hijo_d.vendedor_id or 0, nombre_hijo.lower()))
            if created_h:
                creadas += 1
            upd_h = []
            if hijo_d.activa != hijo_o.activa:
                hijo_d.activa = hijo_o.activa
                upd_h.append('activa')
            if hijo_d.orden != hijo_o.orden:
                hijo_d.orden = hijo_o.orden
                upd_h.append('orden')
            if nombre_hijo and hijo_d.nombre != nombre_hijo:
                hijo_d.nombre = nombre_hijo
                upd_h.append('nombre')
            if upd_h:
                hijo_d.save(update_fields=upd_h)
                if not created_h:
                    actualizadas += 1

        for hijo_d in CategoriaGastoOficina.objects.filter(sucursal=sucursal_destino, parent=raiz_d):
            key = (hijo_d.vendedor_id or 0, (hijo_d.nombre or '').strip().lower())
            if key not in hijos_vistos and hijo_d.activa:
                hijo_d.activa = False
                hijo_d.save(update_fields=['activa'])
                actualizadas += 1

    for raiz_d in CategoriaGastoOficina.objects.filter(sucursal=sucursal_destino, parent__isnull=True):
        if (raiz_d.nombre or '').strip().lower() not in nombres_raiz_espejo and raiz_d.activa:
            raiz_d.activa = False
            raiz_d.save(update_fields=['activa'])
            CategoriaGastoOficina.objects.filter(sucursal=sucursal_destino, parent=raiz_d).update(activa=False)
            actualizadas += 1

    return {'creadas': creadas, 'actualizadas': actualizadas, 'omitido': False}


def _nombres_raices_cierre():
    return {(item[0] or '').strip().lower() for item in ESTRUCTURA_CIERRE_OFICINA}


def _map_hijos_estaticos_cierre():
    out = {}
    for nombre_raiz, hijos in ESTRUCTURA_CIERRE_OFICINA:
        if hijos == '__vendedores__':
            continue
        out[(nombre_raiz or '').strip().lower()] = {
            (h or '').strip().lower() for h in hijos
        }
    return out


def desactivar_categorias_legacy_oficina(sucursal):
    """Desactiva el seed viejo y deja activa solo la estructura del resumen de cierre."""
    raices_cierre = _nombres_raices_cierre()
    hijos_estaticos = _map_hijos_estaticos_cierre()
    raices_vendedor = {(n or '').strip().lower() for n in RAICES_SUBCATEGORIAS_VENDEDOR}

    for raiz in CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent__isnull=True):
        nombre_raiz = (raiz.nombre or '').strip()
        nombre_l = nombre_raiz.lower()

        if nombre_l in RAICES_LEGACY_OFICINA:
            if raiz.activa:
                raiz.activa = False
                raiz.save(update_fields=['activa'])
            CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent=raiz).update(activa=False)
            continue

        if nombre_l not in raices_cierre:
            continue

        for hijo in CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent=raiz):
            nombre_hijo = (hijo.nombre or '').strip()
            nombre_h_l = nombre_hijo.lower()

            if nombre_l in raices_vendedor:
                # Solo desactivar legacy sin vendedor; respetar activa/inactiva manual en filas de vendedor.
                if hijo.vendedor_id:
                    continue
                if nombre_l == 'sueldos' and nombre_h_l in SUBCATEGORIAS_LEGACY_SUELDOS:
                    if hijo.activa:
                        hijo.activa = False
                        hijo.save(update_fields=['activa'])
                elif nombre_l == 'vales' and nombre_h_l in SUBCATEGORIAS_LEGACY_VALES:
                    if hijo.activa:
                        hijo.activa = False
                        hijo.save(update_fields=['activa'])
                continue

            validos = hijos_estaticos.get(nombre_l, set())
            if nombre_h_l not in validos and hijo.activa:
                hijo.activa = False
                hijo.save(update_fields=['activa'])


def _nombre_vendedor_categoria(vendedor):
    fn = getattr(vendedor, 'nombre_completo_vendedor', None)
    if callable(fn):
        return (fn() or str(vendedor)).strip()[:120]
    return str(vendedor).strip()[:120]


def _get_or_create_raiz(sucursal, nombre, orden):
    raiz = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent__isnull=True,
        nombre__iexact=nombre,
    ).first()
    if raiz:
        updates = []
        if raiz.orden != orden:
            raiz.orden = orden
            updates.append('orden')
        if updates:
            raiz.save(update_fields=updates)
        return raiz, False
    try:
        return CategoriaGastoOficina.objects.create(
            sucursal=sucursal,
            nombre=nombre,
            orden=orden,
        ), True
    except IntegrityError:
        existente = CategoriaGastoOficina.objects.filter(
            sucursal=sucursal,
            parent__isnull=True,
            nombre__iexact=nombre,
        ).first()
        if existente:
            return existente, False
        raise


def _get_or_create_hijo(sucursal, parent, nombre, orden, vendedor=None):
    qs = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent=parent,
    )
    if vendedor_id := getattr(vendedor, 'id', None):
        cat = qs.filter(vendedor_id=vendedor_id).first()
    else:
        cat = qs.filter(nombre__iexact=nombre, vendedor__isnull=True).first()
    if cat:
        updates = []
        if cat.nombre != nombre:
            cat.nombre = nombre
            updates.append('nombre')
        if cat.orden != orden:
            cat.orden = orden
            updates.append('orden')
        if vendedor_id and cat.vendedor_id != vendedor_id:
            cat.vendedor_id = vendedor_id
            updates.append('vendedor')
        if updates:
            cat.save(update_fields=updates)
        return cat, False
    try:
        return CategoriaGastoOficina.objects.create(
            sucursal=sucursal,
            parent=parent,
            nombre=nombre,
            orden=orden,
            vendedor=vendedor,
        ), True
    except IntegrityError:
        if vendedor_id:
            existente = qs.filter(vendedor_id=vendedor_id).first()
        else:
            existente = qs.filter(nombre__iexact=nombre, vendedor__isnull=True).first()
        if existente:
            return existente, False
        raise


def _sync_subcategorias_vendedores(sucursal, raiz):
    vendedores = list(
        Vendedor.objects.filter(sucursal=sucursal, is_active=True).order_by('apellido', 'nombre')
    )
    vendedor_ids = {v.id for v in vendedores}
    for i, vendedor in enumerate(vendedores):
        _get_or_create_hijo(
            sucursal,
            raiz,
            _nombre_vendedor_categoria(vendedor),
            i,
            vendedor=vendedor,
        )
    # Desactivar subcategorías de vendedores que ya no están activos.
    obsoletas = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent=raiz,
        vendedor__isnull=False,
    ).exclude(vendedor_id__in=vendedor_ids)
    if obsoletas.exists():
        obsoletas.update(activa=False)
    # Subcategorías genéricas viejas (Productores, Administración…) sin vendedor vinculado.
    CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent=raiz,
        vendedor__isnull=True,
    ).update(activa=False)


def asegurar_estructura_cierre_oficina(sucursal):
    """
    Asegura el árbol de categorías del resumen de cierre (modelo PDF).
    Sincroniza vendedores bajo Sueldos, Vales y Comisiones vendedores.
    Colón usa el árbol ya cargado en Corrientes.
    """
    if sucursal_espeja_categorias_oficina_desde_referencia(sucursal):
        sincronizar_categorias_gasto_oficina_desde_referencia(sucursal)
        return False

    creadas_alguna = False
    for orden, item in enumerate(ESTRUCTURA_CIERRE_OFICINA):
        nombre_raiz, hijos = item
        raiz, creada = _get_or_create_raiz(sucursal, nombre_raiz, orden)
        creadas_alguna = creadas_alguna or creada
        if hijos == '__vendedores__':
            _sync_subcategorias_vendedores(sucursal, raiz)
            continue
        for i, hijo in enumerate(hijos):
            _, creada_h = _get_or_create_hijo(sucursal, raiz, hijo, i)
            creadas_alguna = creadas_alguna or creada_h
    desactivar_categorias_legacy_oficina(sucursal)
    return creadas_alguna


def asegurar_categorias_base(sucursal):
    if sucursal_espeja_categorias_oficina_desde_referencia(sucursal):
        sincronizar_categorias_gasto_oficina_desde_referencia(sucursal)
        return False
    vacia = not CategoriaGastoOficina.objects.filter(sucursal=sucursal).exists()
    asegurar_estructura_cierre_oficina(sucursal)
    return vacia


def asegurar_categoria_vales(sucursal):
    """Mantiene compatibilidad: asegura raíz Vales y subcategorías por vendedor."""
    asegurar_estructura_cierre_oficina(sucursal)
    return CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent__isnull=True,
        nombre__iexact='Vales',
    ).first()


def categoria_gasto_raiz(categoria):
    cat = categoria
    while cat and cat.parent_id:
        cat = cat.parent
    return cat


def categoria_gasto_es_vale(categoria):
    raiz = categoria_gasto_raiz(categoria)
    return bool(raiz and (raiz.nombre or '').strip().lower() == 'vales')


def categoria_gasto_es_ingreso(categoria):
    raiz = categoria_gasto_raiz(categoria)
    return bool(raiz and (raiz.nombre or '').strip().lower() == 'ingresos')


def _raiz_es_vendedores(categoria):
    raiz = categoria_gasto_raiz(categoria)
    if not raiz:
        return False
    return (raiz.nombre or '').strip() in RAICES_SUBCATEGORIAS_VENDEDOR


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
    """Legacy: Sueldos › Productores / Vales sin vendedor vinculado."""
    if not categoria:
        return False
    if getattr(categoria, 'vendedor_id', None):
        return False
    if categoria_gasto_es_vale(categoria):
        return True
    if not categoria.parent_id:
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
        for c in CategoriaGastoOficina.objects.filter(id__in=ids).select_related('parent', 'vendedor')
    }
    for op in opciones:
        cat = cats.get(op['id'])
        op['requiere_productor'] = categoria_gasto_requiere_productor(cat)
        op['es_vale'] = categoria_gasto_es_vale(cat)
        op['es_ingreso'] = categoria_gasto_es_ingreso(cat)
        op['vendedor_id'] = getattr(cat, 'vendedor_id', None)
        if cat and cat.parent_id:
            op['raiz_nombre'] = (cat.parent.nombre or '').strip()
            op['subnombre'] = (cat.nombre or '').strip()
        elif cat:
            op['raiz_nombre'] = (cat.nombre or '').strip()
            op['subnombre'] = (cat.nombre or '').strip()
        else:
            partes = (op.get('label') or '').split(' › ', 1)
            op['raiz_nombre'] = partes[0].strip()
            op['subnombre'] = partes[1].strip() if len(partes) > 1 else partes[0].strip()
        op['busqueda'] = f"{op['raiz_nombre']} {op['subnombre']}".casefold()
    return opciones


def categorias_opciones_grupos(sucursal):
    """Agrupa subcategorías por categoría raíz (para filtro + autocomplete)."""
    opciones = categorias_opciones_con_flags(sucursal)
    orden = []
    mapa = {}
    for op in opciones:
        raiz = op.get('raiz_nombre') or 'Otros'
        if raiz not in mapa:
            mapa[raiz] = []
            orden.append(raiz)
        mapa[raiz].append(op)
    return [{'raiz': raiz, 'opciones': mapa[raiz]} for raiz in orden]


def vendedor_desde_categoria(categoria):
    if categoria and getattr(categoria, 'vendedor_id', None):
        return categoria.vendedor
    return None


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
    if movimiento.tipo == TipoMovimientoCajaEnum.INGRESO:
        total = -total
    elif categoria_gasto_es_ingreso(categoria):
        total = -abs(total)
    fecha = timezone.localdate()
    if movimiento.fecha:
        fecha = timezone.localtime(movimiento.fecha).date()

    if not vendedor:
        vendedor = vendedor_desde_categoria(categoria)

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
    ).select_related('parent', 'vendedor').first()
    if not categoria:
        return None, None, 'La categoría de gasto de oficina no es válida.'

    descripcion = (descripcion or '').strip()
    if not descripcion:
        return None, None, 'La descripción del gasto de oficina es obligatoria.'

    vendedor = vendedor_desde_categoria(categoria)
    if not vendedor and categoria_gasto_requiere_productor(categoria):
        if not vendedor_id_raw:
            if categoria_gasto_es_vale(categoria):
                return None, None, 'Para Vales tenés que elegir el productor.'
            return None, None, 'Para esta categoría tenés que elegir el productor.'
        try:
            vid = int(vendedor_id_raw)
        except (TypeError, ValueError):
            return None, None, 'ID de productor inválido.'
        vendedor = Vendedor.objects.filter(id=vid, sucursal=sucursal).first()
        if not vendedor:
            return None, None, 'El productor elegido no pertenece a esta sucursal.'

    return categoria, vendedor, None
