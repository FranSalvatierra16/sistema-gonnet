"""
Cambia el id (PK / «ficha») de una Propiedad conservando datos y relaciones.

La lógica vive en inmobiliaria.propiedad_pk_rename (también usada al guardar desde el formulario).

Uso (Railway / producción):
  python manage.py renombrar_id_propiedad 464236 112 --sucursal=Corrientes --apply

Sin --apply solo muestra el plan y validaciones (dry-run).

Nota: textos JSON en movimientos (p. ej. concepto_detalle) que guarden el id viejo como
literal no se reescriben; revisar manualmente si aplica.
"""

from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from inmobiliaria.models.propiedad import Propiedad
from inmobiliaria.propiedad_pk_rename import iter_fk_fields_to_propiedad, renombrar_propiedad_pk


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

        fk_specs = list(iter_fk_fields_to_propiedad())
        self.stdout.write(self.style.WARNING(f'Plan: {old_id!r} → {new_id!r} (sucursal: {old.sucursal.nombre})'))
        self.stdout.write(f'Modelos con FK a Propiedad a actualizar: {len(fk_specs)}')

        for model, field in fk_specs:
            attname = field.attname
            n = model._default_manager.filter(**{attname: old_id}).count()
            if n:
                self.stdout.write(f'  - {model._meta.label}: {n} fila(s) en {attname}')

        if not apply:
            self.stdout.write('Dry-run: repetir con --apply para ejecutar.')
            return

        try:
            renombrar_propiedad_pk(old_id, new_id)
        except ValidationError as e:
            msgs = getattr(e, 'message_dict', None) or getattr(e, 'error_dict', None)
            raise CommandError(str(msgs) if msgs else str(e)) from e

        self.stdout.write(self.style.SUCCESS(f'Listo: propiedad ahora tiene id={new_id!r}.'))
