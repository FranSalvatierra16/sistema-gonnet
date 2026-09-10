"""
Realinea gastos, liquidaciones y movimientos de una ficha a su sucursal actual.

Uso:
  python manage.py sincronizar_sucursal_propiedad 3331898
  python manage.py sincronizar_sucursal_propiedad 3331898 --dry-run
"""
from django.core.management.base import BaseCommand, CommandError

from inmobiliaria.models import Propiedad
from inmobiliaria.models.liquidacion import (
    diagnosticar_gastos_propiedad_otras_sucursales,
    sincronizar_sucursal_al_trasladar_propiedad,
)


class Command(BaseCommand):
    help = 'Sincroniza gastos/movimientos de una propiedad a la sucursal actual de la ficha.'

    def add_arguments(self, parser):
        parser.add_argument('propiedad_id', type=str, help='ID de la propiedad (ej. 3331898)')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo muestra diagnóstico; no modifica datos.',
        )

    def handle(self, *args, **options):
        pid = (options['propiedad_id'] or '').strip()
        prop = Propiedad.objects.filter(pk=pid).select_related('sucursal', 'propietario').first()
        if not prop:
            raise CommandError(f'No existe la propiedad #{pid}')
        if not prop.sucursal_id:
            raise CommandError(f'La propiedad #{pid} no tiene sucursal asignada')

        diag = diagnosticar_gastos_propiedad_otras_sucursales(prop)
        self.stdout.write(
            f'Ficha #{prop.id} «{(prop.direccion or "").strip()}» → '
            f'sucursal actual «{prop.sucursal.nombre}» (id={prop.sucursal_id})'
        )
        self.stdout.write(
            f'  Diagnóstico: gastos en esta sucursal={diag["gastos_esta_sucursal"]}, '
            f'gastos en OTRA={diag["gastos_otra_sucursal"]}, '
            f'titular sin ficha en otra={diag["gastos_titular_sin_ficha_otra"]}, '
            f'movs esta={diag["movimientos_esta_sucursal"]}, '
            f'movs otra={diag["movimientos_otra_sucursal"]}'
        )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run: no se modificó nada.'))
            return

        sync = sincronizar_sucursal_al_trasladar_propiedad(prop, prop.sucursal)
        self.stdout.write(
            self.style.SUCCESS(
                f'Realineado: gastos={sync["gastos"]}, liquidaciones={sync["liquidaciones"]}, '
                f'movimientos={sync["movimientos"]}, reservas={sync["reservas"]}, '
                f'contratos={sync["contratos"]}'
            )
        )
        diag2 = diagnosticar_gastos_propiedad_otras_sucursales(prop)
        self.stdout.write(
            f'  Después: gastos esta={diag2["gastos_esta_sucursal"]}, '
            f'gastos otra={diag2["gastos_otra_sucursal"]}, '
            f'movs esta={diag2["movimientos_esta_sucursal"]}, '
            f'movs otra={diag2["movimientos_otra_sucursal"]}'
        )
