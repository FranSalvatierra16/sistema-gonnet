from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
from .caja import MovimientoCaja

# Tipo de operación
class TipoOperacion(models.TextChoices):
    RESERVA_TEMPORAL = 'temporal', 'Reserva Temporal (días)'
    ALQUILER_MENSUAL = 'mensual', 'Alquiler Mensual'

# Contrato de alquiler (operación principal)
class ContratoAlquiler(models.Model):
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE, related_name='contratos')
    inquilino = models.ForeignKey('Inquilino', on_delete=models.CASCADE, related_name='contratos')
    vendedor = models.ForeignKey('Vendedor', on_delete=models.CASCADE, related_name='contratos')
    
    # Fechas del contrato
    fecha_operacion = models.DateField(default=timezone.now, help_text='Fecha en que se realiza la operación')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    duracion_meses = models.PositiveIntegerField()  # 24 meses
    
    # Montos
    precio_mensual = models.DecimalField(max_digits=10, decimal_places=2)
    deposito_garantia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gastos_adicionales = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Estado del contrato
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('finalizado', 'Finalizado'),
        ('rescindido', 'Rescindido')
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activo')
    
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    sucursal = models.ForeignKey('Sucursal', on_delete=models.CASCADE)
    operacion_principal = models.BooleanField(default=False, help_text='Indica si ya se realizó la operación principal (depósito + primer mes)')
    
    class Meta:
        verbose_name = 'Contrato de Alquiler'
        verbose_name_plural = 'Contratos de Alquiler'
        ordering = ['-fecha_creacion']
    
    def __str__(self):
        return f"Contrato {self.id} - {self.propiedad.direccion}"
    
    def total_pagado(self):
        """Calcula el total pagado de todas las cuotas"""
        return sum(cuota.monto_total for cuota in self.cuotas.filter(estado='pagada'))
    
    def cuotas_vencidas(self):
        """Devuelve las cuotas vencidas"""
        return self.cuotas.filter(
            estado='pendiente',
            fecha_vencimiento__lt=timezone.now().date()
        )
    
    def proxima_cuota(self):
        """Devuelve la próxima cuota a pagar"""
        return self.cuotas.filter(estado='pendiente').order_by('fecha_vencimiento').first()

# Cuotas mensuales individuales
class CuotaMensual(models.Model):
    contrato = models.ForeignKey(ContratoAlquiler, on_delete=models.CASCADE, related_name='cuotas')
    numero_cuota = models.PositiveIntegerField()  # 1, 2, 3... hasta 24
    
    # Fechas
    fecha_vencimiento = models.DateField()
    fecha_pago = models.DateField(null=True, blank=True)
    
    # Montos
    monto_base = models.DecimalField(max_digits=10, decimal_places=2)
    recargo_mora = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monto_total = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Estado de pago
    ESTADO_CHOICES = [
        ('pendiente', 'Pendiente'),
        ('pagada', 'Pagada'),
        ('vencida', 'Vencida'),
        ('pagada_con_mora', 'Pagada con Mora')
    ]
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='pendiente')
    
    # Relación con movimiento de caja
    movimiento = models.ForeignKey(MovimientoCaja, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        verbose_name = 'Cuota Mensual'
        verbose_name_plural = 'Cuotas Mensuales'
        ordering = ['contrato', 'numero_cuota']
        unique_together = ('contrato', 'numero_cuota')
    
    def __str__(self):
        return f"Cuota {self.numero_cuota}/{self.contrato.duracion_meses} - {self.contrato.propiedad.direccion}"
    
    def dias_vencido(self):
        """Calcula los días de vencimiento"""
        if self.estado == 'pendiente' and self.fecha_vencimiento < timezone.now().date():
            return (timezone.now().date() - self.fecha_vencimiento).days
        return 0
    
    def calcular_mora(self, tasa_mora_diaria=0.01):
        """Calcula el recargo por mora (1% diario por defecto)"""
        dias = self.dias_vencido()
        if dias > 0:
            return self.monto_base * Decimal(str(tasa_mora_diaria)) * Decimal(str(dias))
        return Decimal('0')

    def actualizar_monto_total(self):
        """Actualiza el monto total considerando mora y descuentos"""
        self.monto_total = self.monto_base + self.recargo_mora - self.descuento
        self.save() 