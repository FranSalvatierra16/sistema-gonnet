from django.core.management.base import BaseCommand
from django.db import transaction
from inmobiliaria.models.propiedad import Reserva
from inmobiliaria.models import MovimientoCaja

class Command(BaseCommand):
    help = 'Actualiza el estado de las reservas que tienen pagos (seña > 0) a "pagada"'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Actualizando estados de reservas con pagos...")
        
        updated_count = 0
        
        with transaction.atomic():
            # Buscar todas las reservas
            all_reservas = Reserva.objects.all()
            
            for reserva in all_reservas:
                # Calcular total pagado
                total_pagado = 0
                
                # Sumar de recibos relacionados
                for recibo in reserva.recibos.all():
                    total_pagado += (recibo.monto_efectivo or 0) + (recibo.monto_cheque or 0) + (recibo.monto_tarjeta or 0) + (recibo.monto_deposito or 0)
                
                # Sumar de MovimientoCaja que mencionen esta reserva
                movimientos = MovimientoCaja.objects.filter(
                    concepto__icontains=f'Reserva #{reserva.id}'
                )
                for mov in movimientos:
                    total_pagado += (mov.monto_efectivo or 0) + (mov.monto_cheque or 0) + (mov.monto_tarjeta or 0) + (mov.monto_deposito or 0)
                
                # Si tiene pagos pero no está marcada como pagada, actualizarla
                if total_pagado > 0 and reserva.estado != 'pagada':
                    old_estado = reserva.estado
                    reserva.estado = 'pagada'
                    reserva.save()
                    updated_count += 1
                    self.stdout.write(f"✅ Reserva #{reserva.id}: ${total_pagado} pagado - Estado: {old_estado} → pagada")
        
        self.stdout.write(f"🎉 {updated_count} reservas actualizadas a estado 'pagada'")
        self.stdout.write("✅ Actualización completada")
