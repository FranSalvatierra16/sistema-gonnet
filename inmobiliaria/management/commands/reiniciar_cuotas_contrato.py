"""
Reinicia todas las cuotas de un contrato: estado pendiente/vencida, sin fecha de pago ni movimiento,
con montos alineados al plan del contrato (precio mensual y trimestres).

Ejemplo:
  python manage.py reiniciar_cuotas_contrato --contrato-id 232 --dry-run
  python manage.py reiniciar_cuotas_contrato --contrato-id 232
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from inmobiliaria.models import ContratoAlquiler
from inmobiliaria.views import _estado_inicial_cuota_por_vencimiento, _montos_cuotas_por_trimestre


class Command(BaseCommand):
    help = 'Reinicia el plan de cuotas de un contrato (no anula movimientos de caja).'

    def add_arguments(self, parser):
        parser.add_argument('--contrato-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        cid = options['contrato_id']
        dry = options['dry_run']

        contrato = ContratoAlquiler.objects.filter(id=cid).first()
        if not contrato:
            self.stderr.write(self.style.ERROR(f'No existe contrato id={cid}'))
            return

        cuotas = list(contrato.cuotas.order_by('numero_cuota'))
        if not cuotas:
            self.stderr.write(self.style.ERROR(f'El contrato #{cid} no tiene cuotas.'))
            return

        hoy = timezone.now().date()
        if int(contrato.duracion_meses or 0) == 9:
            montos = [Decimal(str(contrato.precio_mensual or 0))] * len(cuotas)
        else:
            montos_plan = _montos_cuotas_por_trimestre(contrato)
            montos = []
            for cq in cuotas:
                idx = int(cq.numero_cuota) - 1
                if idx < len(montos_plan):
                    montos.append(montos_plan[idx])
                else:
                    montos.append(Decimal(str(contrato.precio_mensual or 0)))

        pagadas_antes = sum(1 for c in cuotas if c.estado in ('pagada', 'pagada_con_mora'))
        self.stdout.write(
            f'Contrato #{cid}: {len(cuotas)} cuota(s), {pagadas_antes} pagada(s) antes del reinicio.'
        )

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guarda nada.'))
            return

        actualizadas = 0
        for cq, monto in zip(cuotas, montos):
            estado = _estado_inicial_cuota_por_vencimiento(cq.fecha_vencimiento, hoy)
            cq.estado = estado
            cq.fecha_pago = None
            cq.movimiento = None
            cq.monto_base = monto
            cq.monto_total = monto
            cq.recargo_mora = Decimal('0')
            cq.descuento = Decimal('0')
            cq.save()
            actualizadas += 1

        self.stdout.write(self.style.SUCCESS(f'Cuotas reiniciadas: {actualizadas}'))
