"""Tasaciones: monto en pesos o dólares y comisión del productor el día de la tasación."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone


class Tasacion(models.Model):
    """
    Tasación hecha por un productor. La propiedad es texto libre (sin ficha).
    El monto puede cargarse en ARS o USD (con la cotización del día); la
    comisión es un % del monto o un monto fijo y se acredita en la fecha.
    """

    MONEDA_ARS = 'ARS'
    MONEDA_USD = 'USD'
    MONEDA_CHOICES = [
        (MONEDA_ARS, 'Pesos'),
        (MONEDA_USD, 'Dólares'),
    ]
    TIPO_COMISION_PORCENTAJE = 'porcentaje'
    TIPO_COMISION_MONTO = 'monto'
    TIPO_COMISION_CHOICES = [
        (TIPO_COMISION_PORCENTAJE, 'Porcentaje'),
        (TIPO_COMISION_MONTO, 'Monto fijo'),
    ]
    ESTADO_CHOICES = [
        ('confirmada', 'Confirmada'),
        ('anulada', 'Anulada'),
    ]

    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.PROTECT,
        related_name='tasaciones',
    )
    propiedad_nombre = models.CharField(max_length=255, verbose_name='Propiedad')
    vendedor = models.ForeignKey(
        'Vendedor',
        on_delete=models.PROTECT,
        related_name='tasaciones',
        verbose_name='Productor',
    )
    fecha = models.DateField(default=timezone.localdate, verbose_name='Fecha')
    moneda = models.CharField(max_length=3, choices=MONEDA_CHOICES, default=MONEDA_ARS)
    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Monto de la tasación',
        help_text='En la moneda elegida.',
    )
    cotizacion_dolar = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name='Cotización USD → ARS',
    )
    monto_ars = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Monto en pesos',
    )
    tipo_comision = models.CharField(
        max_length=12,
        choices=TIPO_COMISION_CHOICES,
        default=TIPO_COMISION_PORCENTAJE,
    )
    porcentaje_comision = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión (%)',
    )
    comision_monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión fija',
        help_text='En la moneda de la tasación.',
    )
    comision_ars = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Comisión del productor (ARS)',
    )
    cliente_nombre = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Solicitante',
    )
    observaciones = models.TextField(blank=True, default='')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='confirmada')
    comision = models.OneToOneField(
        'ComisionVendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasacion',
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasaciones_creadas',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Tasación'
        verbose_name_plural = 'Tasaciones'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'Tasación #{self.pk} — {self.propiedad_nombre}'

    def _a_pesos(self, valor):
        valor = Decimal(str(valor or 0))
        if self.moneda == self.MONEDA_USD:
            valor *= Decimal(str(self.cotizacion_dolar or 0))
        return valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def recalcular(self):
        """Actualiza monto_ars y comision_ars según moneda, cotización y tipo de comisión."""
        self.monto_ars = self._a_pesos(self.monto)
        if self.tipo_comision == self.TIPO_COMISION_MONTO:
            self.comision_ars = self._a_pesos(self.comision_monto)
        else:
            pct = Decimal(str(self.porcentaje_comision or 0))
            self.comision_ars = (self.monto_ars * pct / Decimal('100')).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
        return self.comision_ars

    @property
    def es_usd(self):
        return self.moneda == self.MONEDA_USD
