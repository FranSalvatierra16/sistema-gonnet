from django.core.management.base import BaseCommand
from django.db import transaction
from inmobiliaria.models import Propiedad, HistorialDisponibilidad
from datetime import timedelta


class Command(BaseCommand):
    help = '🔄 Reconstruye el historial cronológico de disponibilidad para todas las propiedades'

    def add_arguments(self, parser):
        parser.add_argument(
            '--propiedad-id',
            type=int,
            help='ID específico de propiedad para reconstruir (opcional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar qué se haría sin realizar cambios'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔄 INICIANDO RECONSTRUCCIÓN DE HISTORIAL CRONOLÓGICO")
        self.stdout.write("=" * 60)
        
        # Determinar qué propiedades procesar
        if options['propiedad_id']:
            try:
                propiedades = [Propiedad.objects.get(id=options['propiedad_id'])]
                self.stdout.write(f"📍 Procesando propiedad específica: {options['propiedad_id']}")
            except Propiedad.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Propiedad {options['propiedad_id']} no encontrada"))
                return
        else:
            # 🔍 DEBUGGING: Solo Polonia 100 por ahora
            propiedades = Propiedad.objects.filter(id=90808).order_by('id')
            self.stdout.write(f"🔍 DEBUG: Procesando solo Polonia 100: {propiedades.count()} encontradas")
        
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("🔍 MODO DRY-RUN: Solo mostrando cambios, sin aplicar"))
        
        # Procesar cada propiedad
        propiedades_procesadas = 0
        for propiedad in propiedades:
            self.stdout.write("")
            self.stdout.write(f"🏠 PROPIEDAD {propiedad.id}: {propiedad.direccion}")
            self.stdout.write("-" * 50)
            
            try:
                if not options['dry_run']:
                    self.reconstruir_historial_propiedad(propiedad)
                else:
                    self.simular_reconstruccion(propiedad)
                
                propiedades_procesadas += 1
                self.stdout.write(self.style.SUCCESS(f"✅ Propiedad {propiedad.id} procesada correctamente"))
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error en propiedad {propiedad.id}: {str(e)}"))
                continue
        
        # Resumen final
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS(f"🎉 RECONSTRUCCIÓN COMPLETADA"))
        self.stdout.write(f"📊 Propiedades procesadas: {propiedades_procesadas}")
        self.stdout.write(f"📊 Total de propiedades: {propiedades.count()}")
        if options['dry_run']:
            self.stdout.write(self.style.WARNING("⚠️  Recuerda ejecutar sin --dry-run para aplicar los cambios"))

    def reconstruir_historial_propiedad(self, propiedad):
        """
        Reconstruye el historial cronológico para una propiedad específica
        """
        with transaction.atomic():
            # 1️⃣ LIMPIAR historial existente
            historial_anterior = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
            HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
            self.stdout.write(f"🧹 Eliminadas {historial_anterior} entradas de historial anterior")
            
            # 2️⃣ OBTENER disponibilidades y reservas
            disponibilidades = propiedad.disponibilidades.all()
            self.stdout.write(f"📅 {disponibilidades.count()} disponibilidades encontradas")
            
            # Procesar reservas y crear lista de datos de reservas
            reservas_queryset = propiedad.reservas.filter(
                estado__in=['confirmada', 'confirmada_no_pagada', 'pagada']
            )
            reservas = []
            
            for reserva in reservas_queryset:
                # ✅ ESTADOS CORRECTOS: cualquier pago → operación, sin pagos → reservado
                # Verificar múltiples campos: senia, senia_pagada, pagos relacionados, recibos
                tiene_pagos = (
                    (hasattr(reserva, 'senia') and reserva.senia and reserva.senia > 0) or
                    (hasattr(reserva, 'senia_pagada') and reserva.senia_pagada and reserva.senia_pagada > 0) or
                    reserva.recibos.exists() or
                    reserva.pagos.exists()
                )
                
                estado = 'alquilado' if tiene_pagos else 'reservado'
                
                reservas.append({
                    'fecha_inicio': reserva.fecha_inicio,
                    'fecha_fin': reserva.fecha_fin,
                    'estado': estado,
                    'reserva': reserva,
                    'tipo': 'reserva'
                })
            
            self.stdout.write(f"🎯 {len(reservas)} reservas encontradas")
            
            # 3️⃣ FRAGMENTAR DISPONIBILIDADES CON RESERVAS
            historial_fragmentado = []
            
            for disp in disponibilidades:
                # Obtener reservas que intersectan con esta disponibilidad
                reservas_en_disp = [r for r in reservas if 
                    r['fecha_inicio'] < disp.fecha_fin and r['fecha_fin'] > disp.fecha_inicio]
                
                if not reservas_en_disp:
                    # No hay reservas en esta disponibilidad, agregar como período libre completo
                    historial_fragmentado.append({
                        'fecha_inicio': disp.fecha_inicio,
                        'fecha_fin': disp.fecha_fin,
                        'estado': 'libre',
                        'reserva': None,
                        'tipo': 'disponibilidad'
                    })
                else:
                    # Fragmentar la disponibilidad por reservas
                    # Ordenar reservas por fecha de inicio
                    reservas_en_disp.sort(key=lambda x: x['fecha_inicio'])
                    
                    fecha_actual = disp.fecha_inicio
                    
                    for i, reserva_data in enumerate(reservas_en_disp):
                        # Período libre ANTES de la reserva
                        if fecha_actual < reserva_data['fecha_inicio']:
                            historial_fragmentado.append({
                                'fecha_inicio': fecha_actual,
                                'fecha_fin': reserva_data['fecha_inicio'],
                                'estado': 'libre',
                                'reserva': None,
                                'tipo': 'disponibilidad'
                            })
                        
                        # Período de la reserva
                        inicio_reserva = max(fecha_actual, reserva_data['fecha_inicio'])
                        fin_reserva = min(disp.fecha_fin, reserva_data['fecha_fin'])
                        
                        historial_fragmentado.append({
                            'fecha_inicio': inicio_reserva,
                            'fecha_fin': fin_reserva,
                            'estado': reserva_data['estado'],
                            'reserva': reserva_data['reserva'],
                            'tipo': 'reserva'
                        })
                        
                        # Mover fecha actual al final de la reserva
                        fecha_actual = max(fecha_actual, reserva_data['fecha_fin'])
                        
                        # 🔥 NUEVO: Período libre ENTRE reservas
                        # Si hay una siguiente reserva, verificar si hay espacio libre entre ellas
                        if i + 1 < len(reservas_en_disp):
                            proxima_reserva = reservas_en_disp[i + 1]
                            self.stdout.write(f"🔍 DEBUG Polen: Reserva {i+1}: {reserva_data['fecha_inicio']} al {reserva_data['fecha_fin']}")
                            self.stdout.write(f"🔍 DEBUG Polen: Próxima reserva: {proxima_reserva['fecha_inicio']} al {proxima_reserva['fecha_fin']}")
                            self.stdout.write(f"🔍 DEBUG Polen: fecha_actual = {fecha_actual}, próxima_inicio = {proxima_reserva['fecha_inicio']}")
                            
                            if fecha_actual < proxima_reserva['fecha_inicio']:
                                self.stdout.write(f"✅ DEBUG Polen: Creando período libre ENTRE: {fecha_actual} al {proxima_reserva['fecha_inicio']}")
                                historial_fragmentado.append({
                                    'fecha_inicio': fecha_actual,
                                    'fecha_fin': proxima_reserva['fecha_inicio'],
                                    'estado': 'libre',
                                    'reserva': None,
                                    'tipo': 'disponibilidad'
                                })
                                # Actualizar fecha_actual para la próxima iteración
                                fecha_actual = proxima_reserva['fecha_inicio']
                            else:
                                self.stdout.write(f"❌ DEBUG Polen: NO hay espacio libre entre reservas")
                    
                    # Período libre DESPUÉS de todas las reservas
                    if fecha_actual < disp.fecha_fin:
                        historial_fragmentado.append({
                            'fecha_inicio': fecha_actual,
                            'fecha_fin': disp.fecha_fin,
                            'estado': 'libre',
                            'reserva': None,
                            'tipo': 'disponibilidad'
                        })
            
            # 4️⃣ ORDENAR cronológicamente y crear entradas
            historial_fragmentado.sort(key=lambda x: (x['fecha_inicio'], x['fecha_fin']))
            
            for i, periodo in enumerate(historial_fragmentado):
                HistorialDisponibilidad.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=periodo['fecha_inicio'],
                    fecha_fin=periodo['fecha_fin'],
                    estado=periodo['estado'],
                    reserva=periodo['reserva']
                )
                
                estado_emoji = {'libre': '🟡', 'reservado': '🔴', 'alquilado': '🟢'}[periodo['estado']]
                self.stdout.write(f"   {i+1:02d}. {estado_emoji} {periodo['estado'].upper()}: {periodo['fecha_inicio']} al {periodo['fecha_fin']} ({periodo['tipo']})")
            
            self.stdout.write(f"✅ HISTORIAL RECONSTRUIDO: {len(historial_fragmentado)} períodos cronológicos")

    def simular_reconstruccion(self, propiedad):
        """
        Simula la reconstrucción sin hacer cambios (dry-run)
        """
        # Contar entradas actuales
        historial_actual = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
        self.stdout.write(f"🔍 Historial actual: {historial_actual} entradas")
        
        # Obtener disponibilidades y reservas
        disponibilidades = propiedad.disponibilidades.all()
        reservas = propiedad.reservas.filter(
            estado__in=['confirmada', 'confirmada_no_pagada', 'pagada']
        )
        
        self.stdout.write(f"📅 Se recrearían {disponibilidades.count()} períodos libres")
        self.stdout.write(f"🎯 Se recrearían {reservas.count()} períodos reservados/ocupados")
        
        total_nuevo = disponibilidades.count() + reservas.count()
        self.stdout.write(f"📊 RESULTADO: {historial_actual} → {total_nuevo} entradas")
        
        if total_nuevo != historial_actual:
            self.stdout.write(self.style.WARNING(f"⚠️  CAMBIO DETECTADO: Diferencia de {total_nuevo - historial_actual} entradas"))
        else:
            self.stdout.write(self.style.SUCCESS("✅ Sin cambios necesarios"))
