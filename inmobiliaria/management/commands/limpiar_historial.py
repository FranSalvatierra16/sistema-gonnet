from django.core.management.base import BaseCommand
from inmobiliaria.models import HistorialDisponibilidad, Propiedad, Reserva, Disponibilidad
from datetime import timedelta

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
        """
        🔥 LIMPIEZA COMPLETA: Reconstruye disponibilidades Y historial desde cero
        
        1. Guarda las disponibilidades originales (antes de cualquier reserva)
        2. Elimina TODAS las disponibilidades existentes 
        3. Fragmenta las disponibilidades originales según las reservas existentes
        4. Crea el historial basado en las nuevas disponibilidades fragmentadas
        """
        print(f"🔄 LIMPIEZA COMPLETA para propiedad {propiedad.id}")
        
        # 1️⃣ OBTENER todas las reservas existentes
        reservas = propiedad.reservas.filter(
            estado__in=['confirmada', 'confirmada_no_pagada']
        ).order_by('fecha_inicio')
        
        print(f"   📋 Reservas existentes: {reservas.count()}")
        for reserva in reservas:
            print(f"     🎯 Reserva #{reserva.id}: {reserva.fecha_inicio} al {reserva.fecha_fin}")
        
        # 2️⃣ OBTENER rango total de disponibilidad (desde la disponibilidad más temprana hasta la más tardía)
        disponibilidades_actuales = propiedad.disponibilidades.all().order_by('fecha_inicio')
        if not disponibilidades_actuales.exists():
            print(f"   ⚠️ No hay disponibilidades para la propiedad {propiedad.id}")
            return
            
        fecha_inicio_total = disponibilidades_actuales.first().fecha_inicio
        fecha_fin_total = disponibilidades_actuales.last().fecha_fin
        print(f"   📅 Rango total original: {fecha_inicio_total} al {fecha_fin_total}")
        
        # 3️⃣ ELIMINAR todas las disponibilidades existentes
        count_disp = disponibilidades_actuales.count()
        disponibilidades_actuales.delete()
        print(f"   🗑️ Eliminadas {count_disp} disponibilidades existentes")
        
        # 4️⃣ RECREAR disponibilidades fragmentadas correctamente
        self.crear_disponibilidades_fragmentadas(propiedad, fecha_inicio_total, fecha_fin_total, reservas)
        
        # 5️⃣ CREAR historial basado en las nuevas disponibilidades fragmentadas
        disponibilidades_nuevas = propiedad.disponibilidades.all().order_by('fecha_inicio')
        for disp in disponibilidades_nuevas:
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=disp.fecha_inicio,
                fecha_fin=disp.fecha_fin,
                estado='libre'
            )
            print(f"   📅 Historial LIBRE: {disp.fecha_inicio} al {disp.fecha_fin}")
        
        # 6️⃣ CREAR historial para reservas
        for reserva in reservas:
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=reserva.fecha_inicio,
                fecha_fin=reserva.fecha_fin,
                estado='reservado',
                reserva=reserva
            )
            print(f"   🎯 Historial RESERVADO: {reserva.fecha_inicio} al {reserva.fecha_fin} (Reserva #{reserva.id})")
            
        print(f"✅ Limpieza completa terminada para propiedad {propiedad.id}")
    
    def crear_disponibilidades_fragmentadas(self, propiedad, fecha_inicio_total, fecha_fin_total, reservas):
        """
        Crea disponibilidades fragmentadas evitando solapamientos con reservas
        """
        print(f"   🔧 Creando disponibilidades fragmentadas...")
        
        # Lista de períodos ocupados por reservas
        periodos_ocupados = []
        for reserva in reservas:
            periodos_ocupados.append((reserva.fecha_inicio, reserva.fecha_fin))
        
        # Ordenar por fecha de inicio
        periodos_ocupados.sort(key=lambda x: x[0])
        
        # Crear disponibilidades en los gaps entre reservas
        fecha_actual = fecha_inicio_total
        
        for inicio_ocupado, fin_ocupado in periodos_ocupados:
            # Si hay gap antes de la reserva, crear disponibilidad
            if fecha_actual < inicio_ocupado:
                fecha_fin_libre = inicio_ocupado - timedelta(days=1)
                Disponibilidad.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=fecha_actual,
                    fecha_fin=fecha_fin_libre
                )
                print(f"     ✅ Disponibilidad: {fecha_actual} al {fecha_fin_libre}")
            
            # Mover la fecha actual al día después de la reserva
            fecha_actual = fin_ocupado + timedelta(days=1)
        
        # Si queda período libre al final, crearlo
        if fecha_actual <= fecha_fin_total:
            Disponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_actual,
                fecha_fin=fecha_fin_total
            )
            print(f"     ✅ Disponibilidad final: {fecha_actual} al {fecha_fin_total}") 