"""
Marca una cuota de contrato como pagada (sin generar movimiento de caja).

Uso:
  python manage.py marcar_cuota_pagada --contrato 381 --cuota 1 --dry-run
  python manage.py marcar_cuota_pagada --contrato 381 --cuota 1
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from inmobiliaria.models import CuotaMensual


class Command(BaseCommand):
    help = 'Marca una cuota de contrato como pagada (estado + fecha_pago)'

    def add_arguments(self, parser):
        parser.add_argument('--contrato', type=int, required=True, help='ID del contrato')
        parser.add_argument('--cuota', type=int, required=True, help='Número de cuota (ej. 1)')
        parser.add_argument(
            '--fecha',
            type=str,
            default='',
            help='Fecha de pago YYYY-MM-DD (default: hoy)',
        )
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar, no guardar')

    def handle(self, *args, **options):
        contrato_id = options['contrato']
        numero = options['cuota']
        dry_run = options['dry_run']
        fecha_raw = (options.get('fecha') or '').strip()

        cuota = (
            CuotaMensual.objects.select_related('contrato', 'contrato__propiedad')
            .filter(contrato_id=contrato_id, numero_cuota=numero)
            .first()
        )
        if not cuota:
            raise CommandError(f'No existe cuota {numero} del contrato #{contrato_id}')

        if fecha_raw:
            try:
                y, m, d = fecha_raw.split('-')
                fecha_pago = timezone.datetime(int(y), int(m), int(d)).date()
            except Exception as exc:
                raise CommandError(f'Fecha inválida: {fecha_raw}') from exc
        else:
            fecha_pago = timezone.localdate()

        prop = getattr(getattr(cuota.contrato, 'propiedad', None), 'direccion', '') or ''
        self.stdout.write(
            f'Contrato #{contrato_id} {prop} — cuota {numero}: '
            f'estado={cuota.estado} monto={cuota.monto_total} '
            f'venc={cuota.fecha_vencimiento}'
        )

        if cuota.estado in ('pagada', 'pagada_con_mora'):
            self.stdout.write(self.style.WARNING('Ya estaba pagada. No se cambia.'))
            return

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[dry-run] Haría: estado=pagada fecha_pago={fecha_pago}'
                )
            )
            return

        cuota.estado = 'pagada'
        cuota.fecha_pago = fecha_pago
        cuota.save(update_fields=['estado', 'fecha_pago'])
        self.stdout.write(
            self.style.SUCCESS(
                f'OK: cuota {numero} del contrato #{contrato_id} marcada pagada '
                f'({fecha_pago}).'
            )
        )
