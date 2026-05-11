"""
Alinea AlquilerMeses (24 meses) con ContratoAlquiler activo/reservado.

Útil cuando contratos se crearon sin fila info_meses o sin actualizar estado
(bug histórico con hasattr + OneToOne inverso).

Uso en Railway / local:
  python manage.py sincronizar_alquiler_24_con_contratos --dry-run
  python manage.py sincronizar_alquiler_24_con_contratos
  python manage.py sincronizar_alquiler_24_con_contratos --propiedad-id 3087
"""
from django.core.management.base import BaseCommand

from inmobiliaria.models import AlquilerMeses, ContratoAlquiler


def _estado_info_meses_desde_contratos(contratos_qs):
    """
    contratos_qs: queryset de ContratoAlquiler misma propiedad, estado activo/reservado.
    Prioridad: activo > reservado; si hay varios activos, el de mayor id.
    """
    activos = [c for c in contratos_qs if c.estado == 'activo']
    if activos:
        c = max(activos, key=lambda x: x.id)
        return 'ocupado', c
    reservados = [c for c in contratos_qs if c.estado == 'reservado']
    if reservados:
        c = max(reservados, key=lambda x: x.id)
        return 'reservado', c
    return None, None


class Command(BaseCommand):
    help = 'Sincroniza estado/fechas de AlquilerMeses según contratos 24 meses activos o reservados'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Solo listar cambios, sin guardar',
        )
        parser.add_argument(
            '--propiedad-id',
            type=int,
            default=None,
            help='Limitar a una propiedad (ficha / id de propiedad)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        pid_filter = options['propiedad_id']

        base = ContratoAlquiler.objects.filter(
            estado__in=['activo', 'reservado'],
        ).exclude(duracion_meses=9).select_related('propiedad')

        if pid_filter is not None:
            base = base.filter(propiedad_id=pid_filter)

        prop_ids = base.values_list('propiedad_id', flat=True).distinct()
        actualizados = 0
        omitidos = 0

        for prop_id in prop_ids:
            contratos = list(
                ContratoAlquiler.objects.filter(
                    propiedad_id=prop_id,
                    estado__in=['activo', 'reservado'],
                ).exclude(duracion_meses=9).order_by('id')
            )
            if not contratos:
                continue

            nuevo_estado, contrato_ref = _estado_info_meses_desde_contratos(contratos)
            if not contrato_ref:
                omitidos += 1
                continue

            propiedad = contrato_ref.propiedad
            info_meses, created = AlquilerMeses.objects.get_or_create(
                propiedad=propiedad,
                defaults={
                    'disponible': True,
                    'estado': 'disponible',
                    'precio_mensual': contrato_ref.precio_mensual,
                },
            )

            cambios = []
            if info_meses.estado != nuevo_estado:
                cambios.append(f"estado {info_meses.estado!r} -> {nuevo_estado!r}")
            if not info_meses.disponible:
                cambios.append('disponible False -> True')
            if info_meses.fecha_inicio != contrato_ref.fecha_inicio:
                cambios.append(f"fecha_inicio {info_meses.fecha_inicio} -> {contrato_ref.fecha_inicio}")
            if info_meses.fecha_fin != contrato_ref.fecha_fin:
                cambios.append(f"fecha_fin {info_meses.fecha_fin} -> {contrato_ref.fecha_fin}")

            if not cambios and not created:
                self.stdout.write(
                    f"  Propiedad {prop_id}: ya alineada (estado={info_meses.estado}, contrato #{contrato_ref.id})"
                )
                continue

            msg = (
                f"Propiedad {prop_id} ({getattr(propiedad, 'direccion', '')}): "
                + ', '.join(cambios or ['nueva fila AlquilerMeses'])
                + f" [contrato ref #{contrato_ref.id} {contrato_ref.estado}]"
            )
            if dry_run:
                self.stdout.write(self.style.WARNING(f"[dry-run] {msg}"))
            else:
                info_meses.disponible = True
                info_meses.estado = nuevo_estado
                info_meses.fecha_inicio = contrato_ref.fecha_inicio
                info_meses.fecha_fin = contrato_ref.fecha_fin
                if contrato_ref.precio_mensual is not None:
                    info_meses.precio_mensual = contrato_ref.precio_mensual
                info_meses.save()
                self.stdout.write(self.style.SUCCESS(msg))
            actualizados += 1

        if not list(prop_ids):
            self.stdout.write(
                self.style.WARNING('No hay contratos 24 meses (activo/reservado) que coincidan con el filtro.')
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Propiedades consideradas: {len(set(prop_ids))}. "
                f"Cambios aplicados o simulados: {actualizados}. Omitidas sin estado derivable: {omitidos}."
            )
        )
