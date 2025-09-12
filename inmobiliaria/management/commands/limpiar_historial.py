from django.core.management.base import BaseCommand
from inmobiliaria.models import HistorialDisponibilidad, Propiedad, Reserva

class Command(BaseCommand):
    help = 'Limpia y reconstruye el historial de disponibilidad para todas las propiedades'

    def add_arguments(self, parser):
        parser.add_argument(
            '--propiedad-id',
            type=int,
            help='ID de propiedad específica a limpiar (opcional)',
        )

    def handle(self, *args, **options):
        propiedad_id = options.get('propiedad_id')
        
        if propiedad_id:
            # Limpiar una propiedad específica
            try:
                propiedad = Propiedad.objects.get(id=propiedad_id)
                self.limpiar_propiedad(propiedad)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Historial limpiado para propiedad {propiedad_id}')
                )
            except Propiedad.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'❌ No se encontró la propiedad {propiedad_id}')
                )
        else:
            # Limpiar todas las propiedades
            self.stdout.write('🔄 Limpiando historial de todas las propiedades...')
            
            # 1. Eliminar todo el historial existente
            count_historial = HistorialDisponibilidad.objects.count()
            HistorialDisponibilidad.objects.all().delete()
            self.stdout.write(f'🗑️ Eliminadas {count_historial} entradas del historial')
            
            # 2. Reconstruir para todas las propiedades que tienen reservas
            propiedades_con_reservas = Propiedad.objects.filter(
                reservas__estado__in=['confirmada', 'confirmada_no_pagada']
            ).distinct()
            
            for propiedad in propiedades_con_reservas:
                self.reconstruir_historial_propiedad(propiedad)
                self.stdout.write(f'✅ Reconstruido historial para propiedad {propiedad.id}')
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Proceso completado. {propiedades_con_reservas.count()} propiedades procesadas.')
            )

    def limpiar_propiedad(self, propiedad):
        """Limpia y reconstruye el historial de una propiedad específica"""
        # Eliminar historial de esta propiedad
        HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
        
        # Reconstruir
        self.reconstruir_historial_propiedad(propiedad)

    def reconstruir_historial_propiedad(self, propiedad):
        """Reconstruye el historial completo de una propiedad"""
        print(f"🔄 Reconstruyendo historial para propiedad {propiedad.id}")
        
        # Obtener todas las disponibilidades (períodos libres)
        disponibilidades = propiedad.disponibilidades.all().order_by('fecha_inicio')
        for disp in disponibilidades:
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=disp.fecha_inicio,
                fecha_fin=disp.fecha_fin,
                estado='libre'
            )
            print(f"   📅 Agregado período LIBRE: {disp.fecha_inicio} al {disp.fecha_fin}")
        
        # Obtener todas las reservas (períodos reservados)
        reservas = propiedad.reservas.filter(
            estado__in=['confirmada', 'confirmada_no_pagada']
        ).order_by('fecha_inicio')
        
        for reserva in reservas:
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=reserva.fecha_inicio,
                fecha_fin=reserva.fecha_fin,
                estado='reservado',
                reserva=reserva
            )
            print(f"   🎯 Agregado período RESERVADO: {reserva.fecha_inicio} al {reserva.fecha_fin} (Reserva #{reserva.id})") 