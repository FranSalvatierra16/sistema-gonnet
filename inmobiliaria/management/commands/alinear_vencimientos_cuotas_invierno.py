"""
Recalcula fecha_vencimiento de las cuotas de contratos de 9 meses según contrato.fecha_inicio
y contrato.dia_vencimiento (mismo criterio que la vista al crear cuotas).

Sirve para contratos viejos donde los vencimientos quedaron con el año del cobro y no el del contrato.

  python manage.py alinear_vencimientos_cuotas_invierno --contrato-id 99 --dry-run
  python manage.py alinear_vencimientos_cuotas_invierno --contrato-id 99
"""
from calendar import monthrange

from django.core.management.base import BaseCommand
from dateutil.relativedelta import relativedelta

from inmobiliaria.models import ContratoAlquiler


class Command(BaseCommand):
    help = 'Alinea vencimientos de cuotas (9 meses) con fecha_inicio del contrato'

    def add_arguments(self, parser):
        parser.add_argument('--contrato-id', type=int, required=True)
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **options):
        cid = options['contrato_id']
        dry = options['dry_run']

        contrato = ContratoAlquiler.objects.filter(id=cid, duracion_meses=9).first()
        if not contrato:
            self.stderr.write(self.style.ERROR(f'No existe contrato id={cid} con duracion_meses=9'))
            return

        fi = contrato.fecha_inicio
        if not fi:
            self.stderr.write(self.style.ERROR('El contrato no tiene fecha_inicio'))
            return

        d_dia = int(contrato.dia_vencimiento or 5)
        cuotas = list(contrato.cuotas.order_by('numero_cuota'))
        if len(cuotas) != 9:
            self.stdout.write(
                self.style.WARNING(
                    f'Contrato #{cid}: se esperaban 9 cuotas, hay {len(cuotas)}. Se actualizan las que existan.'
                )
            )

        for cuota in cuotas:
            idx = max(0, int(cuota.numero_cuota or 1) - 1)
            ref_mes = fi + relativedelta(months=idx)
            try:
                nueva = ref_mes.replace(day=d_dia)
            except ValueError:
                ult = monthrange(ref_mes.year, ref_mes.month)[1]
                nueva = ref_mes.replace(day=min(d_dia, ult))

            if cuota.fecha_vencimiento == nueva:
                self.stdout.write(f'  Cuota {cuota.numero_cuota}: ya {nueva} OK')
                continue
            self.stdout.write(
                f'  Cuota {cuota.numero_cuota}: {cuota.fecha_vencimiento} -> {nueva}'
            )
            if not dry:
                cuota.fecha_vencimiento = nueva
                cuota.save(update_fields=['fecha_vencimiento'])

        if dry:
            self.stdout.write(self.style.WARNING('Dry-run: no se guardó nada.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Contrato #{cid}: vencimientos actualizados.'))
