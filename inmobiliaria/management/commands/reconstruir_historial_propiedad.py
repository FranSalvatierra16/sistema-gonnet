from django.core.management.base import BaseCommand
from django.db import transaction
from inmobiliaria.models import Propiedad, HistorialDisponibilidad, Reserva


class Command(BaseCommand):
    help = '🔄 Reconstruye el historial de disponibilidad para una propiedad específica por dirección'

    def add_arguments(self, parser):
        parser.add_argument(
            '--direccion',
            type=str,
            help='Dirección de la propiedad (ej: "corrientes 1925")'
        )
        parser.add_argument(
            '--propiedad-id',
            type=int,
            help='ID específico de propiedad para reconstruir (opcional)'
        )

    def handle(self, *args, **options):
        self.stdout.write("🔄 RECONSTRUYENDO HISTORIAL DE PROPIEDAD")
        self.stdout.write("=" * 60)
        
        # Determinar qué propiedad procesar
        if options['propiedad_id']:
            try:
                propiedad = Propiedad.objects.get(id=options['propiedad_id'])
                self.stdout.write(f"📍 Procesando propiedad por ID: {options['propiedad_id']}")
            except Propiedad.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"❌ Propiedad {options['propiedad_id']} no encontrada"))
                return
        elif options['direccion']:
            # Buscar por dirección
            direccion_buscar = options['direccion'].lower()
            propiedades = Propiedad.objects.filter(direccion__icontains=direccion_buscar)
            
            if not propiedades.exists():
                self.stdout.write(self.style.ERROR(f"❌ No se encontró ninguna propiedad con dirección que contenga '{options['direccion']}'"))
                return
            elif propiedades.count() > 1:
                self.stdout.write(self.style.WARNING(f"⚠️  Se encontraron {propiedades.count()} propiedades:"))
                for p in propiedades:
                    self.stdout.write(f"   - ID: {p.id} | Dirección: {p.direccion}")
                self.stdout.write(self.style.ERROR("❌ Por favor, especifica el ID exacto usando --propiedad-id"))
                return
            else:
                propiedad = propiedades.first()
                self.stdout.write(f"📍 Propiedad encontrada: {propiedad.direccion} (ID: {propiedad.id})")
        else:
            self.stdout.write(self.style.ERROR("❌ Debes especificar --direccion o --propiedad-id"))
            return
        
        # Mostrar estado actual
        historial_actual = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
        disponibilidades = propiedad.disponibilidades.filter(es_manual=True).count()
        reservas_activas = propiedad.reservas.filter(eliminada=False).count()
        
        self.stdout.write(f"\n📊 Estado actual:")
        self.stdout.write(f"   - Historial actual: {historial_actual} registros")
        self.stdout.write(f"   - Disponibilidades manuales: {disponibilidades}")
        self.stdout.write(f"   - Reservas activas: {reservas_activas}")
        
        # Reconstruir historial
        self.stdout.write(f"\n🔄 Reconstruyendo historial...")
        self.stdout.write("=" * 60)
        
        with transaction.atomic():
            # Buscar una reserva activa para usar su método de reconstrucción
            reservas_activas_queryset = propiedad.reservas.filter(eliminada=False)
            if reservas_activas_queryset.exists():
                primera_reserva = reservas_activas_queryset.first()
                self.stdout.write(f"📋 Usando método de reconstrucción desde reserva #{primera_reserva.id}")
                primera_reserva.reconstruir_historial_cronologico()
            else:
                # Si no hay reservas, crear historial básico con disponibilidades
                self.stdout.write("📋 No hay reservas activas, creando historial básico desde disponibilidades...")
                HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
                for disp in propiedad.disponibilidades.filter(es_manual=True).order_by('fecha_inicio'):
                    HistorialDisponibilidad.objects.create(
                        propiedad=propiedad,
                        fecha_inicio=disp.fecha_inicio,
                        fecha_fin=disp.fecha_fin,
                        estado='libre'
                    )
                    self.stdout.write(f"   ✅ Período libre: {disp.fecha_inicio} al {disp.fecha_fin}")
        
        # Verificar resultado
        historial_nuevo = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write(self.style.SUCCESS(f"✅ Historial reconstruido exitosamente!"))
        self.stdout.write(f"   - Registros creados: {historial_nuevo}")
        self.stdout.write("=" * 60)
        
        # Mostrar resumen del historial
        self.stdout.write("\n📋 Resumen del historial (primeros 10):")
        historiales = HistorialDisponibilidad.objects.filter(propiedad=propiedad).order_by('fecha_inicio')[:10]
        for h in historiales:
            reserva_info = f" (Reserva #{h.reserva.id})" if h.reserva else ""
            self.stdout.write(f"   - {h.fecha_inicio} al {h.fecha_fin} - {h.estado}{reserva_info}")
        if historial_nuevo > 10:
            self.stdout.write(f"   ... y {historial_nuevo - 10} más")

