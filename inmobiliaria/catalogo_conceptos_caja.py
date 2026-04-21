"""
Catálogo único de conceptos de caja para todas las sucursales.

Se toman los conceptos con sucursal nula (globales) más los asignados a la sucursal
de referencia (por defecto la que contiene «Corrientes» en el nombre).
Si no existe esa sucursal, se conserva el comportamiento anterior (globales + sucursal actual).
"""
from django.db.models import Q

from .models.sucursal import Sucursal


def get_sucursal_referencia_catalogo_conceptos_caja():
    """Sucursal cuyos conceptos se usan como lista maestra para el resto."""
    return Sucursal.objects.filter(nombre__icontains='corrientes').order_by('pk').first()


def q_conceptos_caja_visibles(sucursal_actual):
    """
    Condición ORM para listar/validar conceptos de caja desde cualquier sucursal.
    """
    ref = get_sucursal_referencia_catalogo_conceptos_caja()
    if ref:
        return Q(sucursal__isnull=True) | Q(sucursal_id=ref.pk)
    sid = getattr(sucursal_actual, 'pk', None)
    if sid is None:
        return Q(pk__isnull=False)
    return Q(sucursal__isnull=True) | Q(sucursal_id=sid)


def sucursal_destino_nuevo_concepto_caja(sucursal_actual):
    """FK sucursal al crear conceptos nuevos: la de referencia si existe, si no la del usuario."""
    return get_sucursal_referencia_catalogo_conceptos_caja() or sucursal_actual
