"""
Reimputa CuotaMensual (pagada) desde un MovimientoCaja de operación principal que tenga líneas 1000 en concepto_detalle.

Útil cuando el recibo quedó bien pero las cuotas no se marcaron (bugs viejos con JSON o except: pass).

Ejemplo:
  python manage.py reimputar_cuotas_movimiento --contrato-id 99 --movimiento-id 1923 --dry-run
  python manage.py reimputar_cuotas_movimiento --contrato-id 99 --movimiento-id 1923
"""
from django.core.management.base import BaseCommand

from inmobiliaria.cuotas_imputacion import (
    _normalizar_codigo_concepto_caja,
    imputar_cuotas_mensuales_desde_movimiento_1000,
    payload_conceptos_desde_movimiento_detalle,
)
from inmobiliaria.models import ContratoAlquiler, MovimientoCaja


class Command(BaseCommand):
    help = 'Marca cuotas pagadas según concepto 1000 guardado en un movimiento de caja'

    def add_arguments(self, parser):
        parser.add_argument('--contrato-id', type=int, required=True)
        parser.add_argument('--movimiento-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        cid = options['contrato_id']
        mid = options['movimiento_id']
        dry = options['dry_run']

        contrato = ContratoAlquiler.objects.filter(id=cid).select_related('propiedad').first()
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
                    f'No existe movimiento id={mid} para esa propiedad y texto Contrato #{contrato.id}'
                )
            )
            return

        conceptos = payload_conceptos_desde_movimiento_detalle(mov)
        n1000 = 0
        for it in conceptos:
            rid = it.get('id')
            if rid is None:
                rid = it.get('codigo')
            cod = _normalizar_codigo_concepto_caja(rid)
            moneda = str(it.get('moneda') or 'ARS').strip().upper()
            if cod == '1000' and moneda != 'USD':
                n1000 += 1
        pend = contrato.cuotas.filter(estado__in=['pendiente', 'vencida']).count()
        self.stdout.write(
            f'Contrato #{cid}, movimiento #{mid}: {len(conceptos)} líneas en detalle, '
            f'~{n1000} líneas 1000 ARS, cuotas pendientes/vencidas: {pend}'
        )

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guarda nada.'))
            return

        n = imputar_cuotas_mensuales_desde_movimiento_1000(contrato, mov)
        self.stdout.write(self.style.SUCCESS(f'Cuotas marcadas pagadas: {n}'))
