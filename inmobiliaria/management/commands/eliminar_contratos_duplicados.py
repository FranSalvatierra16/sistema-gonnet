"""
Django management command para rescindir contratos duplicados (misma propiedad + inquilino).
Deja un contrato por grupo (prioridad: con operación principal, luego activo, luego ID mayor)
y marca el resto como rescindidos con motivo "Contrato duplicado".
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Count
from inmobiliaria.models import ContratoAlquiler


class Command(BaseCommand):
    help = 'Rescinde contratos duplicados (misma propiedad e inquilino), dejando uno por grupo'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo mostrar qué se haría, sin modificar',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        if dry_run:
            self.stdout.write(self.style.WARNING('Modo dry-run: no se modificará nada'))

        # Contratos activos o reservados agrupados por (sucursal, propiedad, inquilino)
        qs = (
            ContratoAlquiler.objects
            .filter(estado__in=['activo', 'reservado'])
            .values('sucursal', 'propiedad', 'inquilino')
            .annotate(total=Count('id'))
            .filter(total__gt=1)
        )
        grupos = list(qs)
        if not grupos:
            self.stdout.write(self.style.SUCCESS('No hay grupos de contratos duplicados (activos/reservados).'))
            return

        rescindidos = 0
        for g in grupos:
            contratos = (
                ContratoAlquiler.objects
                .filter(
                    sucursal_id=g['sucursal'],
                    propiedad_id=g['propiedad'],
                    inquilino_id=g['inquilino'],
                    estado__in=['activo', 'reservado'],
                )
                .order_by('-operacion_principal', '-id')
            )
            # Orden: primero con operacion_principal=True, luego por id descendente (más nuevo primero)
            # Python ordena True antes que False, así que el que queremos mantener queda primero
            contratos_list = list(contratos)
            if len(contratos_list) <= 1:
                continue
            mantener = contratos_list[0]
            a_rescindir = contratos_list[1:]
            for c in a_rescindir:
                if dry_run:
                    self.stdout.write(
                        f'  [dry-run] Rescindiría contrato #{c.id} '
                        f'(propiedad {c.propiedad_id}, inquilino {c.inquilino_id}) - se mantiene #{mantener.id}'
                    )
                else:
                    c.estado = 'rescindido'
                    c.fecha_cancelacion = timezone.now().date()
                    c.motivo_cancelacion = f'Contrato duplicado - conservado #{mantener.id}'
                    c.save()
                    self.stdout.write(
                        f'  Rescindido contrato #{c.id} (se mantiene #{mantener.id})'
                    )
                rescindidos += 1

        if dry_run and rescindidos:
            self.stdout.write(self.style.WARNING(f'\nDry-run: se rescindirían {rescindidos} contrato(s). Ejecutá sin --dry-run para aplicar.'))
        elif rescindidos:
            self.stdout.write(self.style.SUCCESS(f'\nListo. Se rescindieron {rescindidos} contrato(s) duplicado(s).'))
        else:
            self.stdout.write(self.style.SUCCESS('No se modificó ningún contrato.'))
