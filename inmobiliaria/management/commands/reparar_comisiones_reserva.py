"""
Genera comisiones faltantes para reservas (alquiler por día, invierno, etc.).

Uso:
  python manage.py reparar_comisiones_reserva --reserva-id 1781 --dry-run
  python manage.py reparar_comisiones_reserva --reserva-id 1781
  python manage.py reparar_comisiones_reserva --desde-id 1700 --hasta-id 1800
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from inmobiliaria.models import ComisionVendedor, MovimientoCaja, Reserva
from inmobiliaria.models.comision import asegurar_comisiones_movimiento_reserva


def _movimientos_reserva(reserva):
    if not reserva.propiedad_id:
        return []
    qs = MovimientoCaja.objects.filter(
        propiedad_id=reserva.propiedad_id,
        sucursal_id=reserva.sucursal_id,
    ).order_by('fecha', 'id')
    ref = f'Operación {reserva.id}'
    return [m for m in qs if ref in (m.concepto or '')]


class Command(BaseCommand):
    help = 'Repara comisiones de vendedor faltantes en reservas por día / invierno'

    def add_arguments(self, parser):
        parser.add_argument('--reserva-id', type=int, help='ID de una reserva puntual')
        parser.add_argument('--desde-id', type=int, help='Rango desde ID de reserva')
        parser.add_argument('--hasta-id', type=int, help='Rango hasta ID de reserva')
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo listar qué se generaría, sin guardar',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        reserva_id = options.get('reserva_id')
        desde = options.get('desde_id')
        hasta = options.get('hasta_id')

        if reserva_id:
            reservas = Reserva.objects.filter(pk=reserva_id)
        elif desde is not None or hasta is not None:
            q = Q()
            if desde is not None:
                q &= Q(pk__gte=desde)
            if hasta is not None:
                q &= Q(pk__lte=hasta)
            reservas = Reserva.objects.filter(q).order_by('id')
        else:
            self.stderr.write('Indicá --reserva-id o un rango --desde-id / --hasta-id')
            return

        reservas = reservas.select_related('vendedor', 'propiedad').exclude(estado='cancelada')
        total_creadas = 0
        total_reservas = 0

        for reserva in reservas:
            if not reserva.vendedor_id:
                self.stdout.write(f'Reserva {reserva.id}: sin vendedor, se omite')
                continue

            antes = ComisionVendedor.objects.filter(reserva=reserva).exclude(estado='cancelada').count()
            movs = _movimientos_reserva(reserva)
            if not movs:
                continue

            if dry_run:
                self.stdout.write(
                    f'Reserva {reserva.id} ({reserva.vendedor}): '
                    f'{antes} comisión(es), revisaría {len(movs)} movimiento(s)'
                )
                continue

            for mov in movs:
                asegurar_comisiones_movimiento_reserva(reserva, mov)

            despues = ComisionVendedor.objects.filter(reserva=reserva).exclude(estado='cancelada').count()
            nuevas = despues - antes
            if nuevas > 0:
                total_reservas += 1
                total_creadas += nuevas
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Reserva {reserva.id}: +{nuevas} comisión(es) '
                        f'({reserva.vendedor}, ${reserva.precio_total})'
                    )
                )

        if dry_run:
            self.stdout.write('Dry-run: no se guardó nada.')
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Listo: {total_creadas} comisión(es) nuevas en {total_reservas} reserva(s).'
                )
            )
