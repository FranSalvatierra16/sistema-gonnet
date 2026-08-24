"""Ventas de propiedades cerradas: precio en USD y honorarios en pesos con cotización."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone


class OperacionVenta(models.Model):
    """
    Registro de una venta cerrada.
    El precio de la operación se carga en dólares; los honorarios del vendedor
    se cargan en pesos eligiendo la cotización del día.
    """

    ESTADO_CHOICES = [
        ('confirmada', 'Confirmada'),
        ('anulada', 'Anulada'),
    ]

    propiedad = models.ForeignKey(
        'Propiedad',
        on_delete=models.PROTECT,
        related_name='operaciones_venta',
        verbose_name='Propiedad',
    )
    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.PROTECT,
        related_name='operaciones_venta',
        verbose_name='Sucursal',
    )
    vendedor = models.ForeignKey(
        'Vendedor',
        on_delete=models.PROTECT,
        related_name='operaciones_venta',
        verbose_name='Vendedor / productor',
        help_text='Quien realizó la venta (recibe los honorarios).',
    )
    fecha_venta = models.DateField(
        default=timezone.localdate,
        verbose_name='Fecha de venta',
    )
    precio_usd = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Precio de venta (USD)',
    )
    cotizacion_dolar = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name='Cotización USD → ARS',
        help_text='Pesos por cada dólar al momento de cargar los honorarios.',
    )
    honorarios_ars = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Honorarios al vendedor (ARS)',
        help_text='Monto en pesos que vos elegís para el vendedor.',
    )
    comprador_nombre = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Comprador',
    )
    escribania = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Escribanía',
    )
    observaciones = models.TextField(
        blank=True,
        default='',
        verbose_name='Observaciones',
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='confirmada',
        verbose_name='Estado',
    )
    comision = models.OneToOneField(
        'ComisionVendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operacion_venta',
        verbose_name='Comisión generada',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operaciones_venta_creadas',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Operación de venta'
        verbose_name_plural = 'Operaciones de venta'
        ordering = ['-fecha_venta', '-id']

    def __str__(self):
        return f'Venta #{self.pk} — {self.propiedad_id} U$S {self.precio_usd}'

    @property
    def precio_ars_equivalente(self):
        if not self.precio_usd or not self.cotizacion_dolar:
            return Decimal('0')
        return (self.precio_usd * self.cotizacion_dolar).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def honorarios_usd_equivalente(self):
        if not self.honorarios_ars or not self.cotizacion_dolar or self.cotizacion_dolar <= 0:
            return Decimal('0')
        return (self.honorarios_ars / self.cotizacion_dolar).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
