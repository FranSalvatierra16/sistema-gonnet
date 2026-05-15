"""
Revierte cuotas marcadas como pagadas por un movimiento de caja que solo tiene depósito,
honorarios, etc., sin líneas 1000/29/1/15 imputables a cuotas.

Caso típico: operación principal con conceptos 10 y 25 pero el sistema marcó cuotas 1–3
como pagadas por error (concepto 1 en secuencia o excedente mal imputado).

Ejemplo contrato 211 / movimiento 1704:
  python manage.py desimputar_cuotas_movimiento_sin_alquiler --contrato-id 211 --movimiento-id 1704
  python manage.py desimputar_cuotas_movimiento_sin_alquiler --contrato-id 211 --movimiento-id 1704 --dry-run
"""
from django.core.management.base import BaseCommand

from inmobiliaria.cuotas_imputacion import (
    desimputar_cuotas_de_movimiento,
    lineas_imputables_desde_movimiento,
    movimiento_tiene_lineas_imputables_cuota,
    payload_conceptos_desde_movimiento_detalle,
)
from inmobiliaria.models import ContratoAlquiler, CuotaMensual, MovimientoCaja


class Command(BaseCommand):
    help = (
        'Quita imputación de cuotas ligadas a un movimiento que no tiene cobro de alquiler/cuota '
        'en concepto_detalle'
    )

    def add_arguments(self, parser):
        parser.add_argument('--contrato-id', type=int, required=True)
        parser.add_argument('--movimiento-id', type=int, required=True)
        parser.add_argument(
            '--forzar',
            action='store_true',
            help='Revertir aunque el movimiento tenga líneas imputables (no recomendado)',
        )
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        cid = options['contrato_id']
        mid = options['movimiento_id']
        forzar = options['forzar']
        dry = options['dry_run']

        contrato = ContratoAlquiler.objects.filter(id=cid).first()
        if not contrato:
            self.stderr.write(self.style.ERROR(f'No existe contrato id={cid}'))
            return

        mov = (
            MovimientoCaja.objects.filter(id=mid, propiedad=contrato.propiedad)
            .filter(concepto__icontains=f'Contrato #{contrato.id}')
            .first()
        )
        if not mov:
            self.stderr.write(
                self.style.ERROR(
                    f'No existe movimiento id={mid} para Contrato #{contrato.id} en esa propiedad'
                )
            )
            return

        conceptos = payload_conceptos_desde_movimiento_detalle(mov)
        imputables = lineas_imputables_desde_movimiento(mov, operacion_principal=False)
        imputables_op = lineas_imputables_desde_movimiento(mov, operacion_principal=True)

        cuotas_mov = list(
            CuotaMensual.objects.filter(contrato=contrato, movimiento=mov).order_by('numero_cuota')
        )
        self.stdout.write(
            f'Contrato #{cid}, movimiento #{mid}: {len(conceptos)} línea(s) en detalle, '
            f'{len(imputables)} imputable(s) (cobro cuota), '
            f'{len(imputables_op)} imputable(s) (regla operación principal).'
        )
        for c in cuotas_mov:
            self.stdout.write(
                f'  Cuota {c.numero_cuota}: estado={c.estado}, '
                f'fecha_pago={c.fecha_pago}, monto_total={c.monto_total}'
            )

        if movimiento_tiene_lineas_imputables_cuota(mov) and not forzar:
            self.stdout.write(
                self.style.WARNING(
                    'El movimiento tiene líneas de alquiler/cuota imputables; no se revierte '
                    '(usá --forzar solo si estás seguro).'
                )
            )
            return

        if not cuotas_mov:
            self.stdout.write(self.style.WARNING('Ninguna cuota apunta a este movimiento.'))
            return

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guarda nada.'))
            return

        n = desimputar_cuotas_de_movimiento(contrato, mov, forzar=forzar)
        self.stdout.write(self.style.SUCCESS(f'Cuotas revertidas a pendiente/vencida: {n}'))
