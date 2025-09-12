from django.core.management.base import BaseCommand
from inmobiliaria.models import HistorialDisponibilidad, Propiedad, Reserva, Disponibilidad
from datetime import timedelta

class Command(BaseCommand):
    help = '🔥 LIMPIEZA BRUTAL: Elimina TODO y reconstruye desde cero'

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
                self.limpiar_propiedad_brutal(propiedad)
                self.stdout.write(
                    self.style.SUCCESS(f'✅ Limpieza brutal completada para propiedad {propiedad_id}')
                )
            except Propiedad.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'❌ No se encontró la propiedad {propiedad_id}')
                )
        else:
            # Limpiar TODAS las propiedades
            self.stdout.write('🔥 LIMPIEZA BRUTAL de todas las propiedades...')
            
            # 1. ELIMINAR absolutamente TODO el historial
            count_historial = HistorialDisponibilidad.objects.count()
            HistorialDisponibilidad.objects.all().delete()
            self.stdout.write(f'🗑️ Eliminadas {count_historial} entradas del historial')
            
            # 2. ELIMINAR absolutamente TODAS las disponibilidades
            count_disponibilidades = Disponibilidad.objects.count()
            Disponibilidad.objects.all().delete()
            self.stdout.write(f'🗑️ Eliminadas {count_disponibilidades} disponibilidades')
            
            # 3. Procesar cada propiedad que tiene reservas
            propiedades_con_reservas = Propiedad.objects.filter(
                reservas__estado__in=['confirmada', 'confirmada_no_pagada']
            ).distinct()
            
            for propiedad in propiedades_con_reservas:
                self.reconstruir_desde_cero(propiedad)
            
            self.stdout.write(
                self.style.SUCCESS(f'✅ Limpieza brutal completada. {propiedades_con_reservas.count()} propiedades procesadas.')
            )

    def limpiar_propiedad_brutal(self, propiedad):
        """Limpieza brutal de una propiedad específica"""
        # Eliminar todo de esta propiedad
        HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
        Disponibilidad.objects.filter(propiedad=propiedad).delete()
        
        # Reconstruir desde cero
        self.reconstruir_desde_cero(propiedad)

    def reconstruir_desde_cero(self, propiedad):
        """
        🔥 RECONSTRUCCIÓN TOTAL desde cero
        
        Asume que NO HAY disponibilidades y crea todo basándose en:
        - Un rango amplio predeterminado (ej: 1 año hacia atrás, 2 años hacia adelante)
        - Las reservas existentes fragmentan ese rango
        """
        print(f"🔥 RECONSTRUCCIÓN TOTAL para propiedad {propiedad.id}")
        
        # 1️⃣ Obtener reservas existentes
        reservas = propiedad.reservas.filter(
            estado__in=['confirmada', 'confirmada_no_pagada']
        ).order_by('fecha_inicio')
        
        if not reservas.exists():
            print(f"   ⚠️ No hay reservas para la propiedad {propiedad.id}, saltando...")
            return
        
        print(f"   📋 Reservas encontradas: {reservas.count()}")
        for reserva in reservas:
            print(f"     🎯 Reserva #{reserva.id}: {reserva.fecha_inicio} al {reserva.fecha_fin}")
        
        # 2️⃣ Definir rango total (desde la primera reserva - 6 meses hasta la última + 6 meses)
        from datetime import datetime, timedelta
        from dateutil.relativedelta import relativedelta
        
        primera_reserva = reservas.first()
        ultima_reserva = reservas.last()
        
        fecha_inicio_total = primera_reserva.fecha_inicio - relativedelta(months=6)
        fecha_fin_total = ultima_reserva.fecha_fin + relativedelta(months=6)
        
        print(f"   📅 Rango total definido: {fecha_inicio_total} al {fecha_fin_total}")
        
        # 3️⃣ Crear disponibilidades fragmentadas evitando las reservas
        fecha_actual = fecha_inicio_total
        
                 for reserva in reservas:
             # Crear disponibilidad ANTES de la reserva (si hay espacio)
             # 🏨 LÓGICA HOTELERA: El día de inicio de reserva está disponible hasta la tarde
             if fecha_actual < reserva.fecha_inicio:
                 fecha_fin_libre = reserva.fecha_inicio  # SIN restar días
                 
                 Disponibilidad.objects.create(
                     propiedad=propiedad,
                     fecha_inicio=fecha_actual,
                     fecha_fin=fecha_fin_libre
                 )
                 print(f"     ✅ Disponibilidad LIBRE: {fecha_actual} al {fecha_fin_libre}")
                 
                 # Crear entrada en el historial
                 HistorialDisponibilidad.objects.create(
                     propiedad=propiedad,
                     fecha_inicio=fecha_actual,
                     fecha_fin=fecha_fin_libre,
                     estado='libre'
                 )
             
             # Crear entrada en el historial para la RESERVA (fechas exactas)
             HistorialDisponibilidad.objects.create(
                 propiedad=propiedad,
                 fecha_inicio=reserva.fecha_inicio,
                 fecha_fin=reserva.fecha_fin,
                 estado='reservado',
                 reserva=reserva
             )
             print(f"     🎯 Historial RESERVADO: {reserva.fecha_inicio} al {reserva.fecha_fin}")
             
             # Mover la fecha actual al día de fin de reserva
             # 🏨 LÓGICA HOTELERA: El día de checkout está disponible desde la mañana
             fecha_actual = reserva.fecha_fin  # SIN sumar días
        
        # 4️⃣ Crear disponibilidad final (después de la última reserva)
        if fecha_actual <= fecha_fin_total:
            Disponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_actual,
                fecha_fin=fecha_fin_total
            )
            print(f"     ✅ Disponibilidad FINAL: {fecha_actual} al {fecha_fin_total}")
            
            # Crear entrada en el historial
            HistorialDisponibilidad.objects.create(
                propiedad=propiedad,
                fecha_inicio=fecha_actual,
                fecha_fin=fecha_fin_total,
                estado='libre'
            )
        
        print(f"✅ Reconstrucción total completada para propiedad {propiedad.id}") 