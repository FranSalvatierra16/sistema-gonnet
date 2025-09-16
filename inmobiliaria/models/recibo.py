from django.db import models
from django.conf import settings


class Recibo(models.Model):
    """
    Modelo para almacenar recibos generados por cada pago
    """
    numero_recibo = models.CharField(max_length=20, unique=True)
    fecha_emision = models.DateTimeField(auto_now_add=True)
    
    # Relaciones
    movimiento_caja = models.OneToOneField('MovimientoCaja', on_delete=models.CASCADE, related_name='recibo')
    reserva = models.ForeignKey('Reserva', on_delete=models.CASCADE, related_name='recibos')
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE, related_name='recibos')
    empleado = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    # Datos del recibo en el momento de emisión
    precio_total_operacion = models.DecimalField(max_digits=10, decimal_places=2, help_text="Precio total de la operación")
    monto_este_pago = models.DecimalField(max_digits=10, decimal_places=2, help_text="Monto pagado en este recibo")
    total_pagado_antes = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Total pagado antes de este recibo")
    saldo_pendiente = models.DecimalField(max_digits=10, decimal_places=2, help_text="Saldo que queda por pagar después de este recibo")
    
    # Conceptos incluidos en este recibo (JSON)
    conceptos_detalle = models.JSONField(default=dict, help_text="Detalles de los conceptos pagados en este recibo")
    
    # Metadata
    observaciones = models.TextField(blank=True)
    
    class Meta:
        db_table = 'inmobiliaria_recibo'
        ordering = ['-fecha_emision']
        verbose_name = "Recibo"
        verbose_name_plural = "Recibos"
    
    def __str__(self):
        return f"Recibo {self.numero_recibo} - {self.fecha_emision.strftime('%d/%m/%Y')}"
    
    def get_numero_secuencial(self):
        """Obtiene el número secuencial de este recibo para la reserva"""
        recibos_anteriores = Recibo.objects.filter(
            reserva=self.reserva,
            fecha_emision__lt=self.fecha_emision
        ).count()
        return recibos_anteriores + 1
