"""
Reinicia todas las cuotas de un contrato: estado pendiente/vencida, sin fecha de pago ni movimiento,
con montos alineados al plan del contrato (precio mensual y trimestres).

Ejemplo:
  python manage.py reiniciar_cuotas_contrato --contrato-id 232 --dry-run
  python manage.py reiniciar_cuotas_contrato --contrato-id 232
"""
from django.core.management.base import BaseCommand

from inmobiliaria.models import ContratoAlquiler
from inmobiliaria.views import _reiniciar_cuotas_contrato


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

        pagadas_antes = sum(1 for c in cuotas if c.estado in ('pagada', 'pagada_con_mora'))
        self.stdout.write(
            f'Contrato #{cid}: {len(cuotas)} cuota(s), {pagadas_antes} pagada(s) antes del reinicio.'
        )

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guarda nada.'))
            return

        n = _reiniciar_cuotas_contrato(contrato)
        self.stdout.write(self.style.SUCCESS(f'Cuotas reiniciadas: {n}'))
