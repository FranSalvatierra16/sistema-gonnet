"""Ventas de propiedades cerradas: precio y honorarios en USD; comisión en ARS con cotización."""
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone


class OperacionVenta(models.Model):
    """
    Registro de una venta cerrada.
    Precio y honorarios se cargan en dólares; con la cotización se calculan
    los honorarios en pesos (lo que va como comisión al vendedor).
    Al confirmar, se sincroniza con el libro del depto (mis propiedades / oficina).
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
        help_text='Vendedor principal (el primero de la lista si hay varios).',
    )
    vendedores = models.ManyToManyField(
        'Vendedor',
        blank=True,
        related_name='operaciones_venta_participacion',
        verbose_name='Vendedores / productores',
        help_text='Uno o más productores que intervinieron en la venta (reparten honorarios).',
    )
    fichado_por = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='operaciones_venta_fichaje',
        verbose_name='Fichaje',
        help_text='Quien fichó la propiedad (puede generar comisión de fichaje).',
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
        help_text='Pesos por cada dólar; se usa para pasar los honorarios a pesos.',
    )
    honorarios_usd = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Honorarios al vendedor (USD)',
        help_text='Monto en dólares que le corresponde al vendedor.',
    )
    honorarios_ars = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        verbose_name='Honorarios al vendedor (ARS)',
        help_text='Resultado: honorarios USD × cotización (comisión en pesos).',
    )
    gastos_escritura_usd = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Gastos de escritura venta (USD)',
        help_text='Se refleja en el libro del departamento.',
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

    def recalcular_honorarios_ars(self):
        """honorarios_ars = honorarios_usd × cotización."""
        usd = Decimal(str(self.honorarios_usd or 0))
        cot = Decimal(str(self.cotizacion_dolar or 0))
        self.honorarios_ars = (usd * cot).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return self.honorarios_ars

    @property
    def precio_ars_equivalente(self):
        if not self.precio_usd or not self.cotizacion_dolar:
            return Decimal('0')
        return (self.precio_usd * self.cotizacion_dolar).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    def lista_vendedores(self):
        """Vendedores de la M2M; si está vacía, cae al vendedor principal."""
        qs = list(self.vendedores.all().order_by('apellido', 'nombre'))
        if qs:
            return qs
        if self.vendedor_id:
            return [self.vendedor]
        return []

    def nombres_vendedores(self):
        return ', '.join(
            f'{(v.apellido or "").strip()}, {(v.nombre or "").strip()}'.strip(', ')
            for v in self.lista_vendedores()
        )
