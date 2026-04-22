"""
Cambia el id (PK / «ficha») de una Propiedad conservando datos y relaciones.

Estrategia (PK CharField con FKs en muchas tablas):
1. Anula temporalmente numero_por_propietario en la fila vieja para no chocar con
   UniqueConstraint(propietario, numero_por_propietario) al existir dos filas un instante.
2. Inserta la nueva fila con bulk_create (no dispara Propiedad.save() → no duplica Precios por defecto).
3. Actualiza todas las ForeignKey / OneToOne hacia Propiedad en la app inmobiliaria.
4. Borra la fila antigua (sin filas hijas que la referencien).

Uso (Railway / producción):
  python manage.py renombrar_id_propiedad 464236 112 --sucursal=Corrientes --apply

Sin --apply solo muestra el plan y validaciones (dry-run).

Nota: textos JSON en movimientos (p. ej. concepto_detalle) que guarden el id viejo como
literal no se reescriben; revisar manualmente si aplica.
"""

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from inmobiliaria.models.propiedad import Propiedad


def _iter_fk_fields_to_propiedad():
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


class Command(BaseCommand):
    help = 'Renombra el id (PK) de una Propiedad y reasigna todas las FKs conocidas en inmobiliaria.'

    def add_arguments(self, parser):
        parser.add_argument('id_viejo', type=str, help='Id actual de la propiedad (ej. 464236)')
        parser.add_argument('id_nuevo', type=str, help='Id destino (ej. 112)')
        parser.add_argument(
            '--sucursal',
            type=str,
            default='',
            help='Nombre o parte del nombre de sucursal esperada (ej. Corrientes). Opcional pero recomendado.',
        )
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Ejecutar cambios (sin esto solo dry-run)',
        )

    def handle(self, *args, **options):
        old_id = (options['id_viejo'] or '').strip()
        new_id = (options['id_nuevo'] or '').strip()
        sucursal_q = (options['sucursal'] or '').strip()
        apply = options['apply']

        if not old_id or not new_id:
            raise CommandError('id_viejo e id_nuevo son obligatorios.')
        if old_id == new_id:
            raise CommandError('Los ids son iguales; no hay nada que hacer.')

        if Propiedad.all_objects.filter(pk=new_id).exists():
            raise CommandError(f'Ya existe una propiedad con id={new_id!r}. No se puede renombrar.')

        try:
            old = Propiedad.all_objects.select_related('sucursal').get(pk=old_id)
        except Propiedad.DoesNotExist as exc:
            raise CommandError(f'No existe propiedad con id={old_id!r}.') from exc

        if sucursal_q:
            nombre = (old.sucursal.nombre or '').lower()
            if sucursal_q.lower() not in nombre:
                raise CommandError(
                    f'La propiedad {old_id!r} pertenece a sucursal {old.sucursal.nombre!r}, '
                    f'no coincide con --sucursal={sucursal_q!r}.'
                )

        fk_specs = list(_iter_fk_fields_to_propiedad())
        self.stdout.write(self.style.WARNING(f'Plan: {old_id!r} → {new_id!r} (sucursal: {old.sucursal.nombre})'))
        self.stdout.write(f'Modelos con FK a Propiedad a actualizar: {len(fk_specs)}')

        for model, field in fk_specs:
            attname = field.attname  # p. ej. propiedad_id
            n = model._default_manager.filter(**{attname: old_id}).count()
            if n:
                self.stdout.write(f'  - {model._meta.label}: {n} fila(s) en {attname}')

        if not apply:
            self.stdout.write(self.style.NOTICE('Dry-run: repetir con --apply para ejecutar.'))
            return

        with transaction.atomic():
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

            total_updates = 0
            for model, field in fk_specs:
                attname = field.attname
                updated = model._default_manager.filter(**{attname: old_id}).update(**{attname: new_id})
                total_updates += updated

            deleted, _details = Propiedad.all_objects.filter(pk=old_id).delete()
            self.stdout.write(self.style.SUCCESS(f'FKs actualizadas en filas: {total_updates}'))
            self.stdout.write(self.style.SUCCESS(f'Propiedad antigua eliminada (filas borradas reportadas: {deleted}).'))

        # Restaurar número en la fila nueva (por si el save del modelo hubiera tocado algo; bulk_create no lo hizo)
        if num_backup is not None:
            Propiedad.all_objects.filter(pk=new_id).update(numero_por_propietario=num_backup)

        self.stdout.write(self.style.SUCCESS(f'Listo: propiedad ahora tiene id={new_id!r}.'))
