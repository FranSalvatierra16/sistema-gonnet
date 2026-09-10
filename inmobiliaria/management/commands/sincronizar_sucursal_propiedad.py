"""
Realinea gastos, liquidaciones y movimientos de una ficha a su sucursal actual.

Uso:
  python manage.py sincronizar_sucursal_propiedad 3331898
"""
from django.core.management.base import BaseCommand, CommandError

from inmobiliaria.models import Propiedad
from inmobiliaria.models.liquidacion import sincronizar_sucursal_al_trasladar_propiedad


class Command(BaseCommand):
    help = 'Sincroniza gastos/movimientos de una propiedad a la sucursal actual de la ficha.'

    def add_arguments(self, parser):
        parser.add_argument('propiedad_id', type=str, help='ID de la propiedad (ej. 3331898)')

    def handle(self, *args, **options):
        pid = (options['propiedad_id'] or '').strip()
        prop = Propiedad.objects.filter(pk=pid).select_related('sucursal').first()
        if not prop:
            raise CommandError(f'No existe la propiedad #{pid}')
        if not prop.sucursal_id:
            raise CommandError(f'La propiedad #{pid} no tiene sucursal asignada')

        sync = sincronizar_sucursal_al_trasladar_propiedad(prop, prop.sucursal)
        self.stdout.write(
            self.style.SUCCESS(
                f'Ficha #{prop.id} → sucursal «{prop.sucursal.nombre}»: '
                f'gastos={sync["gastos"]}, liquidaciones={sync["liquidaciones"]}, '
                f'movimientos={sync["movimientos"]}, reservas={sync["reservas"]}, '
                f'contratos={sync["contratos"]}'
            )
        )
