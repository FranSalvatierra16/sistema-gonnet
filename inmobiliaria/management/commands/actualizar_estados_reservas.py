from django.core.management.base import BaseCommand
from django.db import transaction
from inmobiliaria.models.propiedad import Reserva

class Command(BaseCommand):
    help = 'Actualiza el estado de las reservas que tienen pagos a "pagada"'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Iniciando actualización de estados de reservas...")
        
        # Buscar todas las reservas que tienen recibos (pagos) pero no están marcadas como 'pagada'
        reservas_con_pagos = Reserva.objects.filter(
            recibos__isnull=False  # Tienen recibos (pagos)
        ).exclude(
            estado='pagada'  # Pero NO están marcadas como pagada
        ).distinct()
        
        # También buscar reservas que tienen MovimientoCaja relacionados
        from inmobiliaria.models import MovimientoCaja
        
        # Extraer IDs de reserva desde el campo concepto
        movimientos_reservas = MovimientoCaja.objects.filter(
            concepto__icontains='Reserva #'
        ).values_list('concepto', flat=True)
        
        # Extraer números de reserva del concepto
        ids_reservas_con_movimientos = []
        for concepto in movimientos_reservas:
            import re
            match = re.search(r'Reserva #(\d+)', concepto)
            if match:
                ids_reservas_con_movimientos.append(int(match.group(1)))
        
        reservas_con_movimientos = Reserva.objects.filter(
            id__in=ids_reservas_con_movimientos
        ).exclude(estado='pagada').distinct()
        
        # Combinar ambas consultas
        todas_reservas_con_pagos = (reservas_con_pagos | reservas_con_movimientos).distinct()
        
        self.stdout.write(f"📊 Encontradas {todas_reservas_con_pagos.count()} reservas con pagos pero estado incorrecto")
        
        contador_actualizadas = 0
        
        with transaction.atomic():
            for reserva in todas_reservas_con_pagos:
                estado_anterior = reserva.estado
                reserva.estado = 'pagada'
                reserva.save()
                
                self.stdout.write(
                    f"✅ Reserva #{reserva.id} ({reserva.fecha_inicio} al {reserva.fecha_fin}): "
                    f"{estado_anterior} → pagada"
                )
                contador_actualizadas += 1
        
        self.stdout.write("")
        self.stdout.write(f"🎉 ACTUALIZACIÓN COMPLETADA")
        self.stdout.write(f"📊 Total de reservas actualizadas: {contador_actualizadas}")
        self.stdout.write("")
        self.stdout.write("🔄 Ahora ejecuta: python manage.py reconstruir_historial_cronologico")
        self.stdout.write("   para que todas aparezcan como 'Operación' en el historial")
