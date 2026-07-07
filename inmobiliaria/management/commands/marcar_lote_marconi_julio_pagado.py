"""
Marca pagadas en efectivo (sin sindicato) el lote Marconi 18/07–02/08/2026.

Uso puntual (la migración 0153 hace lo mismo al desplegar):
  python manage.py marcar_lote_marconi_julio_pagado --dry-run
  python manage.py marcar_lote_marconi_julio_pagado
"""
from datetime import date
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Q

from inmobiliaria.models import Reserva


class Command(BaseCommand):
    help = 'Marca pagadas en efectivo las reservas Marconi del 18/07 al 02/08/2026 (una vez)'

    def add_arguments(self, parser):
        parser.add_argument('--sucursal-id', type=int, help='Limitar a una sucursal')
        parser.add_argument('--dry-run', action='store_true', help='Solo mostrar cambios')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        sucursal_id = options.get('sucursal_id')
        fecha_ingreso = date(2026, 7, 18)
        fecha_egreso = date(2026, 8, 2)

        qs = (
            Reserva.objects.filter(
                eliminada=False,
                fecha_fin=fecha_egreso,
                fecha_inicio__gte=fecha_ingreso,
            )
            .filter(
                Q(cliente__apellido__icontains='marconi')
                | Q(cliente__nombre__icontains='marconi')
            )
            .select_related('cliente', 'propiedad')
            .order_by('id')
        )
        if sucursal_id:
            qs = qs.filter(sucursal_id=sucursal_id)

        if not qs.exists():
            self.stdout.write('No se encontraron reservas Marconi en ese rango.')
            return

        propiedad_ids: set[int] = set()
        actualizadas = 0

        for reserva in qs:
            precio = Decimal(str(reserva.precio_total or 0))
            if precio <= Decimal('1.01'):
                continue
            senia = Decimal(str(reserva.senia or 0))
            if (
                (reserva.estado or '') == 'pagada'
                and not reserva.es_alquiler_sindicato
                and senia >= precio - Decimal('0.01')
            ):
                continue

            direccion = getattr(reserva.propiedad, 'direccion', '?')
            if dry_run:
                self.stdout.write(
                    f'  #{reserva.id} {direccion}: '
                    f'{reserva.estado}/seña={senia}/sind={reserva.es_alquiler_sindicato} '
                    f'→ pagada efectivo ${precio}'
                )
                actualizadas += 1
                if reserva.propiedad_id:
                    propiedad_ids.add(reserva.propiedad_id)
                continue

            reserva.es_alquiler_sindicato = False
            reserva.senia = precio
            reserva.cuota_pendiente = Decimal('0')
            reserva.estado = 'pagada'
            reserva.save(
                update_fields=['es_alquiler_sindicato', 'senia', 'cuota_pendiente', 'estado']
            )
            self.stdout.write(
                f'  #{reserva.id} {direccion}: pagada efectivo ${precio}'
            )
            actualizadas += 1
            if reserva.propiedad_id:
                propiedad_ids.add(reserva.propiedad_id)

        if not dry_run and propiedad_ids:
            for propiedad_id in sorted(propiedad_ids):
                primera = (
                    Reserva.objects.filter(propiedad_id=propiedad_id, eliminada=False)
                    .order_by('fecha_inicio')
                    .first()
                )
                if primera:
                    primera.reconstruir_historial_cronologico()

        prefijo = '[dry-run] ' if dry_run else ''
        self.stdout.write(
            self.style.SUCCESS(f'{prefijo}Listo: {actualizadas} reserva(s) actualizada(s).')
        )
