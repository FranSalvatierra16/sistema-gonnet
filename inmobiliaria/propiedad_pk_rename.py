"""
Renombrado atómico del PK (ficha) de Propiedad: clona fila, repunta FKs, borra la vieja.
Usado por el management command y por PropiedadForm al cambiar la ficha desde la UI.
"""

from __future__ import annotations

from django.apps import apps
from django.db import models, transaction
from django.core.exceptions import ValidationError

from inmobiliaria.models.propiedad import Propiedad


def iter_fk_fields_to_propiedad():
    for model in apps.get_models():
        meta = model._meta
        if meta.app_label != 'inmobiliaria' or not meta.managed:
            continue
        for field in meta.get_fields():
            if not getattr(field, 'is_relation', False):
                continue
            if getattr(field, 'many_to_many', False) or getattr(field, 'auto_created', False):
                continue
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            if getattr(field, 'related_model', None) is not Propiedad:
                continue
            if field.model is Propiedad:
                continue
            yield model, field


def renombrar_propiedad_pk(old_id: str, new_id: str) -> None:
    """
    old_id / new_id: valores de PK string (ficha).
    Lanza ValidationError({'id': ...}) si no se puede aplicar.
    """
    old_id = (old_id or '').strip()
    new_id = (new_id or '').strip()
    if not old_id or not new_id:
        raise ValidationError({'id': 'El ID de la propiedad no puede quedar vacío.'})
    if old_id == new_id:
        return
    if Propiedad.all_objects.filter(pk=new_id).exists():
        raise ValidationError({'id': 'Ya existe una propiedad con este ID.'})

    fk_specs = list(iter_fk_fields_to_propiedad())

    with transaction.atomic():
        try:
            old = Propiedad.all_objects.get(pk=old_id)
        except Propiedad.DoesNotExist as exc:
            raise ValidationError({'id': 'La propiedad a renombrar ya no existe.'}) from exc

        num_backup = old.numero_por_propietario
        Propiedad.all_objects.filter(pk=old_id).update(numero_por_propietario=None)
        old.refresh_from_db()

        kwargs = {}
        for f in Propiedad._meta.local_concrete_fields:
            if f.primary_key:
                continue
            kwargs[f.name] = f.value_from_object(old)

        clone = Propiedad(pk=new_id, **kwargs)
        Propiedad.all_objects.bulk_create([clone])

        for model, field in fk_specs:
            attname = field.attname
            model._default_manager.filter(**{attname: old_id}).update(**{attname: new_id})

        Propiedad.all_objects.filter(pk=old_id).delete()

    if num_backup is not None:
        Propiedad.all_objects.filter(pk=new_id).update(numero_por_propietario=num_backup)
