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
            propiedades = Propiedad.objects.all().order_by('id')
            self.stdout.write(f"📋 Procesando TODAS las propiedades: {propiedades.count()} encontradas")
        
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
            
            # 2️⃣ OBTENER todos los períodos (disponibilidades + reservas)
            periodos = []
            
            # Agregar disponibilidades (períodos libres)
            disponibilidades = propiedad.disponibilidades.all()
            for disp in disponibilidades:
                periodos.append({
                    'fecha_inicio': disp.fecha_inicio,
                    'fecha_fin': disp.fecha_fin,
                    'estado': 'libre',
                    'reserva': None,
                    'tipo': 'disponibilidad',
                    'objeto': disp
                })
            
            self.stdout.write(f"📅 {disponibilidades.count()} disponibilidades encontradas")
            
            # Agregar reservas (períodos reservados/alquilados)
            reservas = propiedad.reservas.filter(
                estado__in=['confirmada', 'confirmada_no_pagada', 'pagada']
            )
            for reserva in reservas:
                # ✅ ESTADOS CORRECTOS: sin pagos → reservado, con pagos → operación
                tiene_pagos = reserva.recibos.exists() or reserva.pagos.exists()
                estado = 'alquilado' if tiene_pagos else 'reservado'
                periodos.append({
                    'fecha_inicio': reserva.fecha_inicio,
                    'fecha_fin': reserva.fecha_fin,
                    'estado': estado,
                    'reserva': reserva,
                    'tipo': 'reserva',
                    'objeto': reserva
                })
            
            self.stdout.write(f"🎯 {reservas.count()} reservas encontradas")
            
            # 3️⃣ ORDENAR cronológicamente
            periodos.sort(key=lambda x: (x['fecha_inicio'], x['fecha_fin']))
            
            # 4️⃣ CREAR entradas de historial ordenadas
            for i, periodo in enumerate(periodos):
                HistorialDisponibilidad.objects.create(
                    propiedad=propiedad,
                    fecha_inicio=periodo['fecha_inicio'],
                    fecha_fin=periodo['fecha_fin'],
                    estado=periodo['estado'],
                    reserva=periodo['reserva']
                )
                
                estado_emoji = {'libre': '🟢', 'reservado': '🟡', 'alquilado': '🔴'}[periodo['estado']]
                self.stdout.write(f"   {i+1:02d}. {estado_emoji} {periodo['estado'].upper()}: {periodo['fecha_inicio']} al {periodo['fecha_fin']} ({periodo['tipo']})")
            
            self.stdout.write(f"✅ HISTORIAL RECONSTRUIDO: {len(periodos)} períodos cronológicos")

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
