"""
Aplica el mínimo de comisión de productor a líneas ya existentes (incl. confirmadas).

Uso:
  python manage.py aplicar_piso_comisiones --dry-run
  python manage.py aplicar_piso_comisiones --sucursal-id 2 --solo-confirmadas
  python manage.py aplicar_piso_comisiones --vendedor-id 16 --solo-confirmadas
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from inmobiliaria.models.comision import aplicar_piso_comisiones_productor_existentes


class Command(BaseCommand):
    help = (
        'Sube al piso de comisión ($10.000 por productor/línea) las comisiones '
        'por día debajo del mínimo. No toca fichaje ni pagadas.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo listar cambios, sin guardar',
        )
        parser.add_argument('--sucursal-id', type=int, help='Filtrar por sucursal')
        parser.add_argument('--vendedor-id', type=int, help='Filtrar por vendedor')
        parser.add_argument(
            '--todos-roles',
            action='store_true',
            help='También invierno / 24 meses / general (no solo por día)',
        )
        parser.add_argument(
            '--solo-confirmadas',
            action='store_true',
            help='Solo confirmadas (recomendado para backfill)',
        )
        parser.add_argument(
            '--incluir-pendientes',
            action='store_true',
            help='También pendientes (además de confirmadas, salvo --solo-confirmadas)',
        )
        parser.add_argument(
            '--monto-desde',
            type=str,
            default='1',
            help='Ignorar montos menores o iguales (default 1, evita basura $0,04)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        solo_confirmadas = options['solo_confirmadas']
        incluir_confirmadas = True
        if options['incluir_pendientes'] and not solo_confirmadas:
            solo_confirmadas = False
            incluir_confirmadas = True
        elif not solo_confirmadas and not options['incluir_pendientes']:
            # Default seguro: solo confirmadas
            solo_confirmadas = True

        monto_desde = Decimal(str(options['monto_desde'] or '0'))

        cambios = aplicar_piso_comisiones_productor_existentes(
            solo_por_dia=not options['todos_roles'],
            incluir_confirmadas=incluir_confirmadas,
            solo_confirmadas=solo_confirmadas,
            sucursal_id=options.get('sucursal_id'),
            vendedor_id=options.get('vendedor_id'),
            monto_desde=monto_desde,
            dry_run=dry_run,
        )

        if not cambios:
            self.stdout.write(self.style.SUCCESS('Nada para actualizar.'))
            return

        for ch in cambios:
            op = f"res#{ch['reserva_id']}" if ch['reserva_id'] else f"ctr#{ch['contrato_id']}"
            self.stdout.write(
                f"comision #{ch['id']} vend={ch['vendedor_id']} {op} "
                f"{ch['rol']} {ch['estado']} part={ch['participacion']}% "
                f"${ch['antes']} → ${ch['despues']} (mín ${ch['minimo_op']})"
            )

        pref = '[DRY-RUN] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(f'{pref}Actualizadas {len(cambios)} comisión(es).')
        )
