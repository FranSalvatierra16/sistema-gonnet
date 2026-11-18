"""
Repara liquidaciones divididas cuyo monto_propietario fue pisado con el total.

Uso:
  python manage.py reparar_liquidaciones_divididas --dry-run
  python manage.py reparar_liquidaciones_divididas
  python manage.py reparar_liquidaciones_divididas --ids 1838 1833
  python manage.py reparar_liquidaciones_divididas --sucursal-id 1
"""
from django.core.management.base import BaseCommand

from inmobiliaria.liquidacion_operacion import reparar_montos_liquidaciones_divididas
from inmobiliaria.models.sucursal import Sucursal


class Command(BaseCommand):
    help = (
        'Restaura monto_propietario de liquidaciones partidas que quedaron '
        'con el total de la operación (duplicadas al reimprimir).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo lista qué se repararía, sin guardar.',
        )
        parser.add_argument(
            '--ids',
            nargs='+',
            type=int,
            default=None,
            help='IDs de liquidaciones a revisar (ej. 1838 1833).',
        )
        parser.add_argument(
            '--sucursal-id',
            type=int,
            default=None,
            help='Limitar a una sucursal.',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        ids = options.get('ids')
        sucursal = None
        sid = options.get('sucursal_id')
        if sid:
            sucursal = Sucursal.objects.filter(pk=sid).first()
            if not sucursal:
                self.stderr.write(self.style.ERROR(f'Sucursal {sid} no encontrada.'))
                return

        reparadas = reparar_montos_liquidaciones_divididas(
            dry_run=dry_run,
            ids=ids,
            sucursal=sucursal,
        )
        if not reparadas:
            self.stdout.write(self.style.SUCCESS('No hay liquidaciones divididas para reparar.'))
            return

        modo = 'DRY-RUN' if dry_run else 'APLICADO'
        self.stdout.write(self.style.WARNING(f'[{modo}] {len(reparadas)} liquidación(es):'))
        for info in reparadas:
            self.stdout.write(
                f"  #{info['id']}: ${info['antes']} → ${info['despues']}"
                f" (total división={info.get('total_division')}, "
                f"reserva={info.get('reserva_id')})"
            )
        if dry_run:
            self.stdout.write(
                self.style.NOTICE('Volvé a correr sin --dry-run para guardar los cambios.')
            )
        else:
            self.stdout.write(self.style.SUCCESS('Reparación guardada.'))
