"""Helpers compartidos para gastos de oficina (panel y movimientos de caja)."""
import unicodedata
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.db import IntegrityError
from django.db.models import ProtectedError
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


def _es_sucursal_corrientes(sucursal):
    return bool(sucursal and 'corrientes' in _normalizar_nombre_sucursal(sucursal.nombre))


def _es_sucursal_colon(sucursal):
    return bool(sucursal and 'colon' in _normalizar_nombre_sucursal(sucursal.nombre))


def sucursales_espejo_categorias_oficina(sucursal):
    """
    Sucursales que deben compartir el mismo árbol de categorías (Corrientes ↔ Colón).
    """
    if not sucursal:
        return []
    from inmobiliaria.models.sucursal import Sucursal

    if not (_es_sucursal_corrientes(sucursal) or _es_sucursal_colon(sucursal)):
        return []

    pares = []
    for s in Sucursal.objects.exclude(pk=sucursal.pk).order_by('pk'):
        if _es_sucursal_corrientes(sucursal) and _es_sucursal_colon(s):
            pares.append(s)
        elif _es_sucursal_colon(sucursal) and _es_sucursal_corrientes(s):
            pares.append(s)
    return pares


def par_sucursales_reparto_gasto_oficina(sucursal):
    """
    Si la sucursal es Colón o Corrientes, retorna
    {'colon': Sucursal, 'corrientes': Sucursal, 'local_key': 'colon'|'corrientes'}.
    Si no aplica, None.
    """
    if not sucursal:
        return None
    from inmobiliaria.models.sucursal import Sucursal

    if _es_sucursal_colon(sucursal):
        otra = Sucursal.objects.filter(nombre__icontains='corrientes').order_by('pk').first()
        if not otra:
            return None
        return {'colon': sucursal, 'corrientes': otra, 'local_key': 'colon'}
    if _es_sucursal_corrientes(sucursal):
        otra = Sucursal.objects.filter(nombre__icontains='colon').order_by('pk').first()
        if not otra:
            return None
        return {'colon': otra, 'corrientes': sucursal, 'local_key': 'corrientes'}
    return None


def defaults_porcentajes_reparto_gasto_oficina(sucursal):
    """Sucursal logueada 100%, la otra 0%."""
    par = par_sucursales_reparto_gasto_oficina(sucursal)
    if not par:
        return None
    if par['local_key'] == 'colon':
        return {'colon': Decimal('100'), 'corrientes': Decimal('0')}
    return {'colon': Decimal('0'), 'corrientes': Decimal('100')}


def parse_porcentaje_reparto(raw):
    """Parsea un % desde POST. Retorna Decimal o None si vacío/inválido."""
    s = (raw or '').strip().replace(',', '.')
    if not s:
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, TypeError, ValueError):
        return None


def validar_porcentajes_reparto_gasto_oficina(pct_colon_raw, pct_corrientes_raw, sucursal):
    """
    Valida el reparto Colón/Corrientes.
    Retorna (pct_colon, pct_corrientes, error_msg).
    Si la sucursal no es del par, retorna (None, None, None) sin error.
    """
    par = par_sucursales_reparto_gasto_oficina(sucursal)
    if not par:
        return None, None, None

    defaults = defaults_porcentajes_reparto_gasto_oficina(sucursal)
    pct_colon = parse_porcentaje_reparto(pct_colon_raw)
    pct_corrientes = parse_porcentaje_reparto(pct_corrientes_raw)
    if pct_colon is None:
        pct_colon = defaults['colon']
    if pct_corrientes is None:
        pct_corrientes = defaults['corrientes']

    if pct_colon < 0 or pct_corrientes < 0:
        return None, None, 'Los porcentajes de reparto no pueden ser negativos.'
    if pct_colon > 100 or pct_corrientes > 100:
        return None, None, 'Los porcentajes de reparto no pueden superar 100.'

    suma = pct_colon + pct_corrientes
    if abs(suma - Decimal('100')) > Decimal('0.05'):
        return None, None, 'Los porcentajes Colón + Corrientes tienen que sumar 100%.'

    # Ajuste fino para que sumen exactamente 100
    pct_colon = pct_colon.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    pct_corrientes = (Decimal('100') - pct_colon).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return pct_colon, pct_corrientes, None


def _monto_por_porcentaje(total, porcentaje, es_resto=False, total_ya_asignado=None):
    """Calcula el monto de una parte. Si es_resto, usa total - ya_asignado para cuadrar."""
    total = Decimal(str(total or 0))
    if es_resto and total_ya_asignado is not None:
        return (total - Decimal(str(total_ya_asignado))).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    pct = Decimal(str(porcentaje or 0))
    return (total * pct / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def _encontrar_categoria_espejo(cat, sucursal_destino, nombre_buscar=None):
    """Misma categoría en otra sucursal (por nombre de raíz / hijo)."""
    if not cat or not sucursal_destino:
        return None
    nombre = (nombre_buscar if nombre_buscar is not None else cat.nombre or '').strip()
    if not nombre:
        return None

    if cat.parent_id:
        parent_nombre = (cat.parent.nombre or '').strip()
        parent_d = CategoriaGastoOficina.objects.filter(
            sucursal=sucursal_destino,
            parent__isnull=True,
            nombre__iexact=parent_nombre,
        ).first()
        if not parent_d:
            return None
        if cat.vendedor_id:
            vend_d = _resolver_vendedor_espejo(sucursal_destino, cat.vendedor)
            if not vend_d:
                return None
            return CategoriaGastoOficina.objects.filter(
                sucursal=sucursal_destino,
                parent=parent_d,
                vendedor=vend_d,
            ).first()
        return CategoriaGastoOficina.objects.filter(
            sucursal=sucursal_destino,
            parent=parent_d,
            nombre__iexact=nombre,
            vendedor__isnull=True,
        ).first()

    return CategoriaGastoOficina.objects.filter(
        sucursal=sucursal_destino,
        parent__isnull=True,
        nombre__iexact=nombre,
    ).first()


def _asegurar_parent_espejo(cat, sucursal_destino):
    """Crea la raíz espejo si hace falta (para subcategorías nuevas)."""
    if not cat.parent_id:
        return None
    parent = cat.parent
    parent_d, _ = _get_or_create_raiz(
        sucursal_destino,
        (parent.nombre or '').strip(),
        parent.orden,
    )
    if parent_d.activa != parent.activa:
        parent_d.activa = parent.activa
        parent_d.save(update_fields=['activa'])
    return parent_d


def propagar_categoria_oficina_a_espejos(
    cat,
    *,
    accion='upsert',
    nombre_anterior=None,
    cascade_hijos=False,
):
    """
    Replica alta / renombre / activación / baja de una categoría en Colón ↔ Corrientes.
    Las subcategorías ligadas a vendedor se omiten (se sincronizan por productor).
    """
    if not cat or getattr(cat, 'vendedor_id', None):
        return 0

    espejos = sucursales_espejo_categorias_oficina(cat.sucursal)
    if not espejos:
        return 0

    afectados = 0
    for destino in espejos:
        if accion == 'upsert':
            if cat.parent_id:
                parent_d = _asegurar_parent_espejo(cat, destino)
                if not parent_d:
                    continue
                hijo_d, created = _get_or_create_hijo(
                    destino,
                    parent_d,
                    (cat.nombre or '').strip(),
                    cat.orden,
                )
                upd = []
                if hijo_d.activa != cat.activa:
                    hijo_d.activa = cat.activa
                    upd.append('activa')
                if hijo_d.orden != cat.orden:
                    hijo_d.orden = cat.orden
                    upd.append('orden')
                if upd:
                    hijo_d.save(update_fields=upd)
                if created or upd:
                    afectados += 1
            else:
                raiz_d, created = _get_or_create_raiz(
                    destino,
                    (cat.nombre or '').strip(),
                    cat.orden,
                )
                upd = []
                if raiz_d.activa != cat.activa:
                    raiz_d.activa = cat.activa
                    upd.append('activa')
                if raiz_d.orden != cat.orden:
                    raiz_d.orden = cat.orden
                    upd.append('orden')
                if upd:
                    raiz_d.save(update_fields=upd)
                if created or upd:
                    afectados += 1

        elif accion == 'rename':
            espejo = _encontrar_categoria_espejo(
                cat, destino, nombre_buscar=nombre_anterior or cat.nombre
            )
            if not espejo:
                # Si no existía, crearla con el nombre nuevo.
                propagar_categoria_oficina_a_espejos(cat, accion='upsert')
                afectados += 1
                continue
            nuevo = (cat.nombre or '').strip()
            if nuevo and espejo.nombre != nuevo:
                espejo.nombre = nuevo
                espejo.save(update_fields=['nombre'])
                afectados += 1

        elif accion == 'toggle':
            espejo = _encontrar_categoria_espejo(cat, destino)
            if not espejo:
                propagar_categoria_oficina_a_espejos(cat, accion='upsert')
                afectados += 1
                continue
            if espejo.activa != cat.activa:
                espejo.activa = cat.activa
                espejo.save(update_fields=['activa'])
                afectados += 1
            if cascade_hijos and espejo.parent_id is None:
                CategoriaGastoOficina.objects.filter(
                    sucursal=destino, parent=espejo
                ).update(activa=cat.activa)

        elif accion == 'delete':
            espejo = _encontrar_categoria_espejo(
                cat, destino, nombre_buscar=nombre_anterior or cat.nombre
            )
            if not espejo:
                continue
            num_gastos = espejo.gastos.count()
            if espejo.parent_id is None:
                num_gastos += GastoOficina.objects.filter(categoria__parent=espejo).count()
            if num_gastos:
                # No borrar si hay gastos: desactivar para no romper historial.
                if espejo.activa:
                    espejo.activa = False
                    espejo.save(update_fields=['activa'])
                    if espejo.parent_id is None:
                        CategoriaGastoOficina.objects.filter(
                            sucursal=destino, parent=espejo
                        ).update(activa=False)
                    afectados += 1
                continue
            try:
                espejo.delete()
                afectados += 1
            except ProtectedError:
                if espejo.activa:
                    espejo.activa = False
                    espejo.save(update_fields=['activa'])
                    afectados += 1

    return afectados


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


def siguiente_orden_categoria(sucursal, parent=None):
    """Siguiente orden para agregar al final del listado (raíz o subcategorías del mismo padre)."""
    from django.db.models import Max

    agg = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent=parent,
    ).aggregate(m=Max('orden'))
    max_ord = agg['m']
    return 0 if max_ord is None else max_ord + 1


def reubicar_raices_personalizadas_al_final(sucursal):
    """
    Raíces creadas manualmente (fuera del árbol de cierre) quedan al final,
    en orden de creación.
    """
    raices_cierre = _nombres_raices_cierre()
    raices = list(
        CategoriaGastoOficina.objects.filter(sucursal=sucursal, parent__isnull=True)
    )
    oficiales = [
        r
        for r in raices
        if (r.nombre or '').strip().lower() in raices_cierre
        or (r.nombre or '').strip().lower() in RAICES_LEGACY_OFICINA
    ]
    personalizadas = sorted(
        [r for r in raices if r not in oficiales],
        key=lambda x: x.id,
    )
    if not personalizadas:
        return False

    max_orden = max((r.orden for r in oficiales), default=-1)
    next_orden = max_orden + 1
    changed = False
    for raiz in personalizadas:
        if raiz.orden != next_orden:
            raiz.orden = next_orden
            raiz.save(update_fields=['orden'])
            changed = True
        next_orden += 1
    return changed


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
    """Desactiva categorías del seed viejo (raíces legacy y subcategorías obsoletas de Sueldos/Vales)."""
    raices_cierre = _nombres_raices_cierre()
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

def _nombre_vendedor_categoria(vendedor, nombres_usados=None):
    """
    Nombre visible de la subcategoría por vendedor.
    Si hay homónimos en la misma raíz, agrega #id para respetar el unique
    (sucursal, parent, nombre) y no tirar IntegrityError al sincronizar.
    """
    fn = getattr(vendedor, 'nombre_completo_vendedor', None)
    if callable(fn):
        base = (fn() or '').strip()
    else:
        base = str(vendedor).strip()
    if not base:
        base = f'Vendedor #{getattr(vendedor, "id", "")}'.strip()
    nombre = base[:120]
    if nombres_usados is None:
        return nombre
    key = nombre.casefold()
    if key in nombres_usados:
        sufijo = f' #{getattr(vendedor, "id", "")}'
        nombre = (base[: max(0, 120 - len(sufijo))] + sufijo)[:120]
        key = nombre.casefold()
    nombres_usados.add(key)
    return nombre


def _get_or_create_raiz(sucursal, nombre, orden):
    raiz = CategoriaGastoOficina.objects.filter(
        sucursal=sucursal,
        parent__isnull=True,
        nombre__iexact=nombre,
    ).first()
    if raiz:
        # No pisar ``orden``: el usuario puede reordenar categorías a mano.
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
        nombre_final = nombre
        if cat.nombre != nombre:
            # Si el nombre ya lo usa otra subcategoría, uniquificar con #id.
            conflicto = qs.filter(nombre__iexact=nombre).exclude(pk=cat.pk).exists()
            if conflicto and vendedor_id:
                sufijo = f' #{vendedor_id}'
                nombre_final = (nombre[: max(0, 120 - len(sufijo))] + sufijo)[:120]
            if cat.nombre != nombre_final:
                cat.nombre = nombre_final
                updates.append('nombre')
        # Solo sincronizar orden automático en filas de vendedor (listado alfabético).
        # Las demás respetan el orden manual del usuario.
        if vendedor_id and cat.orden != orden:
            cat.orden = orden
            updates.append('orden')
        if vendedor_id and cat.vendedor_id != vendedor_id:
            cat.vendedor_id = vendedor_id
            updates.append('vendedor')
        if updates:
            try:
                cat.save(update_fields=updates)
            except IntegrityError:
                if vendedor_id and 'nombre' in updates:
                    sufijo = f' #{vendedor_id}'
                    cat.nombre = (nombre[: max(0, 120 - len(sufijo))] + sufijo)[:120]
                    try:
                        cat.save(update_fields=updates)
                    except IntegrityError:
                        pass
                else:
                    pass
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
            if existente:
                return existente, False
            # Nombre tomado por otra fila: reintentar con #id.
            sufijo = f' #{vendedor_id}'
            nombre_alt = (nombre[: max(0, 120 - len(sufijo))] + sufijo)[:120]
            try:
                return CategoriaGastoOficina.objects.create(
                    sucursal=sucursal,
                    parent=parent,
                    nombre=nombre_alt,
                    orden=orden,
                    vendedor=vendedor,
                ), True
            except IntegrityError:
                existente = qs.filter(vendedor_id=vendedor_id).first()
                if existente:
                    return existente, False
                existente = qs.filter(nombre__iexact=nombre_alt).first()
                if existente:
                    return existente, False
                raise
        existente = qs.filter(nombre__iexact=nombre, vendedor__isnull=True).first()
        if existente:
            return existente, False
        existente = qs.filter(nombre__iexact=nombre).first()
        if existente:
            return existente, False
        raise


def _sync_subcategorias_vendedores(sucursal, raiz):
    vendedores = list(
        Vendedor.objects.filter(sucursal=sucursal, is_active=True).order_by('apellido', 'nombre', 'id')
    )
    vendedor_ids = {v.id for v in vendedores}
    nombres_usados = set()
    for i, vendedor in enumerate(vendedores):
        _get_or_create_hijo(
            sucursal,
            raiz,
            _nombre_vendedor_categoria(vendedor, nombres_usados),
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
    # Solo desactivar subcategorías legacy genéricas (Productores, Administración…), no las creadas a mano.
    nombre_raiz_l = (raiz.nombre or '').strip().lower()
    legacy_nombres = set()
    if nombre_raiz_l == 'sueldos':
        legacy_nombres = SUBCATEGORIAS_LEGACY_SUELDOS
    elif nombre_raiz_l == 'vales':
        legacy_nombres = SUBCATEGORIAS_LEGACY_VALES
    if legacy_nombres:
        for hijo in CategoriaGastoOficina.objects.filter(
            sucursal=sucursal,
            parent=raiz,
            vendedor__isnull=True,
            activa=True,
        ):
            if (hijo.nombre or '').strip().lower() in legacy_nombres:
                hijo.activa = False
                hijo.save(update_fields=['activa'])


def asegurar_estructura_cierre_oficina(sucursal):
    """
    Asegura el árbol de categorías del resumen de cierre (modelo PDF).
    Sincroniza vendedores bajo Sueldos, Vales y Comisiones vendedores.
    Colón usa el árbol ya cargado en Corrientes.
    """
    if not sucursal:
        return False

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


def categorias_opciones_grupos(sucursal, opciones=None):
    """Agrupa subcategorías por categoría raíz (para filtro + autocomplete)."""
    if opciones is None:
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


def asegurar_categorias_oficina_si_faltan(sucursal):
    """
    Solo sincroniza la estructura si la sucursal no tiene categorías todavía.
    Evita get_or_create + sync de vendedores en cada GET de nuevo movimiento.
    """
    if not sucursal:
        return False
    if CategoriaGastoOficina.objects.filter(sucursal=sucursal).exists():
        return False
    return asegurar_categorias_base(sucursal)


def vendedor_desde_categoria(categoria):
    if categoria and getattr(categoria, 'vendedor_id', None):
        return categoria.vendedor
    return None


def _fmt_pct_reparto(pct):
    """Formato legible de porcentaje (80 o 80.5)."""
    if pct is None:
        return ''
    s = f'{Decimal(str(pct)):.2f}'.rstrip('0').rstrip('.')
    return s


def registrar_gasto_oficina_desde_movimiento(
    movimiento,
    categoria,
    descripcion,
    observaciones='',
    vendedor=None,
    usuario=None,
    porcentaje_colon=None,
    porcentaje_corrientes=None,
):
    """
    Crea el GastoOficina del movimiento. Si hay reparto Colón/Corrientes,
    crea también el gasto en la otra sucursal con su % (sin movimiento de caja allí).
    El egreso de caja queda 100% en la sucursal donde se cargó.
    """
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

    descripcion = (descripcion or categoria.nombre_ruta())[:255]
    observaciones = observaciones or ''
    sucursal_local = movimiento.sucursal
    par = par_sucursales_reparto_gasto_oficina(sucursal_local)

    # Sin par o sin porcentajes: comportamiento histórico (100% local).
    if not par or porcentaje_colon is None or porcentaje_corrientes is None:
        return GastoOficina.objects.create(
            sucursal=sucursal_local,
            categoria=categoria,
            fecha=fecha,
            monto=total,
            descripcion=descripcion,
            observaciones=observaciones,
            movimiento_caja=movimiento,
            vendedor=vendedor,
            usuario_creacion=usuario,
            porcentaje=Decimal('100') if par else None,
            monto_total=total if par else None,
        )

    pct_colon = Decimal(str(porcentaje_colon))
    pct_corrientes = Decimal(str(porcentaje_corrientes))
    local_key = par['local_key']
    pct_local = pct_colon if local_key == 'colon' else pct_corrientes
    pct_otra = pct_corrientes if local_key == 'colon' else pct_colon
    sucursal_otra = par['corrientes'] if local_key == 'colon' else par['colon']

    monto_local = _monto_por_porcentaje(total, pct_local)
    monto_otra = _monto_por_porcentaje(total, pct_otra, es_resto=True, total_ya_asignado=monto_local)

    nota_reparto = (
        f'Reparto: Colón {_fmt_pct_reparto(pct_colon)}% / '
        f'Corrientes {_fmt_pct_reparto(pct_corrientes)}%'
        f' (total ${abs(total):.2f}).'
    )
    obs_local = f'{observaciones}\n{nota_reparto}'.strip() if observaciones else nota_reparto

    gasto_local = GastoOficina.objects.create(
        sucursal=sucursal_local,
        categoria=categoria,
        fecha=fecha,
        monto=monto_local,
        descripcion=descripcion,
        observaciones=obs_local,
        movimiento_caja=movimiento,
        vendedor=vendedor,
        usuario_creacion=usuario,
        porcentaje=pct_local,
        monto_total=total,
    )

    if abs(monto_otra) < Decimal('0.005'):
        return gasto_local

    cat_otra = _encontrar_categoria_espejo(categoria, sucursal_otra)
    if not cat_otra:
        # Sin categoría espejo no se puede imputar a la otra sucursal.
        gasto_local.observaciones = (
            f'{obs_local}\n'
            f'AVISO: no se pudo crear el gasto en {sucursal_otra.nombre} '
            f'(falta categoría espejo).'
        ).strip()
        gasto_local.save(update_fields=['observaciones', 'fecha_modificacion'])
        return gasto_local

    vendedor_otra = None
    if vendedor:
        vendedor_otra = _resolver_vendedor_espejo(sucursal_otra, vendedor)

    obs_otra = (
        f'{observaciones}\n{nota_reparto}\n'
        f'Origen: movimiento de caja #{movimiento.id} en {sucursal_local.nombre}.'
    ).strip()

    gasto_otra = GastoOficina.objects.create(
        sucursal=sucursal_otra,
        categoria=cat_otra,
        fecha=fecha,
        monto=monto_otra,
        descripcion=descripcion,
        observaciones=obs_otra,
        movimiento_caja=None,
        vendedor=vendedor_otra,
        usuario_creacion=usuario,
        porcentaje=pct_otra,
        monto_total=total,
        gasto_relacionado=gasto_local,
    )
    gasto_local.gasto_relacionado = gasto_otra
    gasto_local.save(update_fields=['gasto_relacionado', 'fecha_modificacion'])
    return gasto_local


def eliminar_gastos_oficina_de_movimiento(movimiento):
    """Borra gastos de oficina del movimiento y su par en la otra sucursal."""
    if not movimiento:
        return
    gastos = list(
        GastoOficina.objects.filter(movimiento_caja=movimiento).select_related('gasto_relacionado')
    )
    ids_borrar = set()
    for g in gastos:
        ids_borrar.add(g.id)
        if g.gasto_relacionado_id:
            ids_borrar.add(g.gasto_relacionado_id)
        # También pares que apuntan a este gasto
        for pareja_id in GastoOficina.objects.filter(
            gasto_relacionado_id=g.id
        ).values_list('id', flat=True):
            ids_borrar.add(pareja_id)
    if ids_borrar:
        GastoOficina.objects.filter(id__in=ids_borrar).delete()


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
