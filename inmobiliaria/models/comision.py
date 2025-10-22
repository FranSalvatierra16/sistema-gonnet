from django.db import models
from django.utils import timezone
from decimal import Decimal
from .persona import Vendedor
from .propiedad import Reserva
from .caja import MovimientoCaja


class ComisionVendedor(models.Model):
    """
    Modelo para registrar las comisiones ganadas por los vendedores en cada operación
    """
    vendedor = models.ForeignKey(
        Vendedor, 
        on_delete=models.CASCADE, 
        related_name='comisiones',
        verbose_name="Vendedor"
    )
    reserva = models.ForeignKey(
        Reserva, 
        on_delete=models.CASCADE, 
        related_name='comisiones_vendedor',
        verbose_name="Reserva"
    )
    movimiento_caja = models.ForeignKey(
        MovimientoCaja,
        on_delete=models.CASCADE,
        related_name='comisiones_vendedor',
        verbose_name="Movimiento de Caja",
        null=True,
        blank=True
    )
    
    # Montos de la operación
    monto_total_operacion = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto Total de la Operación"
    )
    porcentaje_comision = models.DecimalField(
        max_digits=5, 
        decimal_places=2,
        verbose_name="Porcentaje de Comisión (%)"
    )
    monto_comision = models.DecimalField(
        max_digits=12, 
        decimal_places=2,
        verbose_name="Monto de Comisión"
    )
    
    # Información adicional
    concepto_operacion = models.CharField(
        max_length=200,
        verbose_name="Concepto de la Operación"
    )
    fecha_operacion = models.DateTimeField(
        default=timezone.now,
        verbose_name="Fecha de la Operación"
    )
    fecha_calculo = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Cálculo"
    )
    
    # Estado de la comisión
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('confirmada', 'Confirmada'),
        ('pagada', 'Pagada'),
        ('cancelada', 'Cancelada'),
    ]
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='confirmada',
        verbose_name="Estado"
    )
    
    # Observaciones
    observaciones = models.TextField(
        blank=True,
        verbose_name="Observaciones"
    )
    
    class Meta:
        verbose_name = "Comisión de Vendedor"
        verbose_name_plural = "Comisiones de Vendedores"
        ordering = ['-fecha_operacion']
        unique_together = ['vendedor', 'reserva', 'movimiento_caja']
    
    def __str__(self):
        return f"Comisión {self.id} - {self.vendedor.nombre_completo_vendedor()} - ${self.monto_comision}"
    
    def save(self, *args, **kwargs):
        # Calcular automáticamente el monto de comisión si no está definido
        if not self.monto_comision and self.monto_total_operacion and self.porcentaje_comision:
            self.monto_comision = (self.monto_total_operacion * self.porcentaje_comision) / Decimal('100')
        super().save(*args, **kwargs)
    
    @classmethod
    def crear_comision(cls, vendedor, reserva, movimiento_caja, monto_total, concepto=""):
        """
        Método helper para crear una comisión automáticamente
        """
        if not vendedor.comision:
            return None
            
        # Verificar si ya existe una comisión para esta operación
        comision_existente = cls.objects.filter(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja
        ).first()
        
        if comision_existente:
            return comision_existente
        
        comision = cls.objects.create(
            vendedor=vendedor,
            reserva=reserva,
            movimiento_caja=movimiento_caja,
            monto_total_operacion=monto_total,
            porcentaje_comision=vendedor.comision,
            concepto_operacion=concepto or f"Operación {reserva.id}",
            fecha_operacion=movimiento_caja.fecha if movimiento_caja else timezone.now()
        )
        
        return comision
    
    def get_monto_comision_mensual(self, año, mes):
        """
        Obtiene el monto de comisión para un mes específico
        """
        return ComisionVendedor.objects.filter(
            vendedor=self.vendedor,
            fecha_operacion__year=año,
            fecha_operacion__month=mes,
            estado__in=['confirmada', 'pagada']
        ).aggregate(
            total=models.Sum('monto_comision')
        )['total'] or Decimal('0')
