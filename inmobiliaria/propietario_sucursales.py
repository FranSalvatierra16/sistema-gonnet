"""Vinculación de propietarios entre sucursales Colón / Corrientes."""
from django.db.models import Q

from inmobiliaria.models.persona import Propietario
from inmobiliaria.models.sucursal import Sucursal

Q_SUCURSALES_COLON_CORRIENTES = (
    Q(nombre__icontains='colon') | Q(nombre__icontains='corrientes')
)

CAMPOS_SYNC_PROPIETARIO = (
    'nombre',
    'apellido',
    'fecha_nacimiento',
    'email',
    'celular',
    'observaciones',
    'localidad',
    'provincia',
    'domicilio',
    'codigo_postal',
    'cuit',
    'tipo_ins',
    'tipo_doc',
    'dni',
    'cuenta_banco',
    'cuenta_titular',
    'cuenta_cbu_alias',
    'cuenta_numero',
)


def usuario_en_colon_o_corrientes(user):
    nombre_suc = (getattr(getattr(user, 'sucursal', None), 'nombre', None) or '').lower()
    return 'colon' in nombre_suc or 'corrientes' in nombre_suc


def puede_gestionar_sucursales_propietario(user):
    return bool(user and usuario_en_colon_o_corrientes(user))


def get_sucursales_colon_corrientes():
    return Sucursal.objects.filter(Q_SUCURSALES_COLON_CORRIENTES).order_by('nombre')


def _hermanos_propietario(propietario):
    dni = (propietario.dni or '').strip()
    if dni:
        return Propietario.objects.filter(dni=dni)
    return Propietario.objects.filter(
        apellido__iexact=propietario.apellido,
        nombre__iexact=propietario.nombre,
    )


def propietario_sucursales_vinculadas(propietario):
    if not propietario or not propietario.pk:
        return set()
    return set(_hermanos_propietario(propietario).values_list('sucursal_id', flat=True))


def _buscar_ficha_en_sucursal(propietario, sucursal_id):
    dni = (propietario.dni or '').strip()
    qs = Propietario.objects.filter(sucursal_id=sucursal_id)
    if dni:
        return qs.filter(dni=dni).first()
    return qs.filter(
        apellido__iexact=propietario.apellido,
        nombre__iexact=propietario.nombre,
    ).first()


def _copiar_datos_propietario(destino, origen):
    for campo in CAMPOS_SYNC_PROPIETARIO:
        setattr(destino, campo, getattr(origen, campo))
    destino.save()


def sincronizar_propietario_en_sucursales(propietario, sucursal_ids):
    """Crea o actualiza fichas del mismo propietario en las sucursales indicadas."""
    if not propietario or not propietario.pk:
        return

    sucursal_ids = {int(sid) for sid in sucursal_ids if str(sid).isdigit()}
    if not sucursal_ids:
        return

    for sucursal_id in sucursal_ids:
        if sucursal_id == propietario.sucursal_id:
            continue
        hermano = _buscar_ficha_en_sucursal(propietario, sucursal_id)
        if hermano:
            _copiar_datos_propietario(hermano, propietario)
        else:
            hermano = Propietario(sucursal_id=sucursal_id)
            _copiar_datos_propietario(hermano, propietario)


def desvincular_sucursales_no_seleccionadas(propietario, sucursal_ids):
    """
    Quita fichas hermanas en sucursales desmarcadas, solo si no tienen propiedades.
    Devuelve nombres de sucursales que no se pudieron desvincular por tener propiedades.
    """
    from inmobiliaria.models.propiedad import Propiedad

    ids_gestionables = set(get_sucursales_colon_corrientes().values_list('id', flat=True))
    seleccionadas = {int(sid) for sid in sucursal_ids if str(sid).isdigit()} & ids_gestionables
    seleccionadas.add(propietario.sucursal_id)

    omitidas = []
    hermanos = _hermanos_propietario(propietario).filter(sucursal_id__in=ids_gestionables)
    for hermano in hermanos:
        if hermano.pk == propietario.pk:
            continue
        if hermano.sucursal_id in seleccionadas:
            continue
        if Propiedad.objects.filter(propietario=hermano).exists():
            omitidas.append(hermano.sucursal.nombre)
            continue
        hermano.delete()
    return omitidas


def nombres_sucursales_vinculadas(propietario):
    ids = propietario_sucursales_vinculadas(propietario)
    if not ids:
        return []
    return list(
        Sucursal.objects.filter(id__in=ids).order_by('nombre').values_list('nombre', flat=True)
    )
