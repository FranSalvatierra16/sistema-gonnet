"""
Cartera compartida por sucursal.

Todos los usuarios de la misma sucursal ven y editan la misma cartera
(Mis propiedades / deptos de oficina). El titular de Corrientes es el usuario #15.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Count, Q

from inmobiliaria.models.cartera_usuario import CarteraPropiedadUsuario

# Titular fijo por nombre de sucursal (substring case-insensitive).
CARTERA_TITULAR_USER_ID_POR_SUCURSAL = {
    'corrientes': 15,
}


def _clave_sucursal(sucursal) -> str:
    return (getattr(sucursal, 'nombre', None) or '').strip().lower()


def usuario_titular_cartera(sucursal):
    """
    Usuario cuya cartera es la compartida de la sucursal.
    Corrientes → id 15. Otras: el usuario de la sucursal con más ítems de cartera
    (empate → menor id); si nadie tiene, el usuario activo de menor id de esa sucursal.
    """
    if not sucursal:
        return None

    User = get_user_model()
    nombre = _clave_sucursal(sucursal)

    for clave, uid in CARTERA_TITULAR_USER_ID_POR_SUCURSAL.items():
        if clave in nombre:
            u = User.objects.filter(pk=uid).first()
            if u:
                return u

    # Fallback: quien ya tenga más propiedades de esta sucursal en cartera
    top = (
        CarteraPropiedadUsuario.objects.filter(propiedad__sucursal=sucursal)
        .values('usuario_id')
        .annotate(n=Count('id'))
        .order_by('-n', 'usuario_id')
        .first()
    )
    if top and top.get('usuario_id'):
        u = User.objects.filter(pk=top['usuario_id']).first()
        if u:
            return u

    # Último recurso: primer usuario activo de la sucursal
    return (
        User.objects.filter(sucursal=sucursal, is_active=True)
        .order_by('id')
        .first()
    )


def sincronizar_cartera_compartida_sucursal(sucursal):
    """
    Une en el titular todas las propiedades de cartera de la sucursal
    y elimina filas de otros usuarios (misma sucursal de propiedad).
    """
    titular = usuario_titular_cartera(sucursal)
    if not titular or not sucursal:
        return titular

    otros = CarteraPropiedadUsuario.objects.filter(
        propiedad__sucursal=sucursal,
    ).exclude(usuario=titular).select_related('propiedad')

    for item in otros.iterator(chunk_size=200):
        if CarteraPropiedadUsuario.objects.filter(
            usuario=titular, propiedad_id=item.propiedad_id
        ).exists():
            continue
        CarteraPropiedadUsuario.objects.create(
            usuario=titular,
            propiedad_id=item.propiedad_id,
            porcentaje=item.porcentaje,
            propietario_id=item.propietario_id,
        )

    CarteraPropiedadUsuario.objects.filter(
        propiedad__sucursal=sucursal,
    ).exclude(usuario=titular).delete()

    return titular


def qs_cartera_sucursal(sucursal, *, sincronizar=True):
    """QuerySet de CarteraPropiedadUsuario de la cartera compartida de la sucursal."""
    if not sucursal:
        return CarteraPropiedadUsuario.objects.none()
    titular = (
        sincronizar_cartera_compartida_sucursal(sucursal)
        if sincronizar
        else usuario_titular_cartera(sucursal)
    )
    if not titular:
        return CarteraPropiedadUsuario.objects.none()
    return CarteraPropiedadUsuario.objects.filter(
        usuario=titular,
        propiedad__sucursal=sucursal,
    )
