from decimal import Decimal

from django.conf import settings
from django.db import models


class CategoriaGastoOficina(models.Model):
    """Categoría de gasto de oficina; puede tener subcategorías (parent → hijos)."""

    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.CASCADE,
        related_name='categorias_gasto_oficina',
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subcategorias',
        verbose_name='Categoría padre',
    )
    nombre = models.CharField(max_length=120)
    activa = models.BooleanField(default=True)
    orden = models.PositiveSmallIntegerField(default=0)
    vendedor = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='categorias_gasto_oficina',
        verbose_name='Vendedor vinculado',
        help_text='Subcategorías de Sueldos, Vales o Comisiones generadas por vendedor.',
    )

    class Meta:
        verbose_name = 'Categoría gasto oficina'
        verbose_name_plural = 'Categorías gasto oficina'
        ordering = ['orden', 'nombre']
        constraints = [
            models.UniqueConstraint(
                fields=['sucursal', 'parent', 'nombre'],
                name='uniq_categoria_gasto_oficina_sucursal_parent_nombre',
            ),
        ]

    def __str__(self):
        return self.nombre_ruta()

    def nombre_ruta(self):
        if self.parent_id:
            return f'{self.parent.nombre} › {self.nombre}'
        return self.nombre

    def es_raiz(self):
        return self.parent_id is None


class GastoOficina(models.Model):
    """Gasto imputable a la oficina (sueldos, servicios, contables, etc.)."""

    sucursal = models.ForeignKey(
        'Sucursal',
        on_delete=models.CASCADE,
        related_name='gastos_oficina',
    )
    categoria = models.ForeignKey(
        CategoriaGastoOficina,
        on_delete=models.PROTECT,
        related_name='gastos',
        verbose_name='Categoría / subcategoría',
    )
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=14, decimal_places=2)
    descripcion = models.CharField(max_length=255)
    observaciones = models.TextField(blank=True)
    movimiento_caja = models.ForeignKey(
        'MovimientoCaja',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_oficina_vinculados',
        help_text='Egreso de caja que pagó este gasto.',
    )
    vendedor = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_oficina_sueldo',
        verbose_name='Productor / vendedor',
        help_text='Obligatorio para sueldos a productores.',
    )
    porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='% imputado a esta sucursal',
        help_text='Porcentaje del total en el reparto Colón / Corrientes.',
    )
    monto_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Monto total del movimiento',
        help_text='Monto completo antes de repartir entre sucursales.',
    )
    gasto_relacionado = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_reparto_pareja',
        verbose_name='Gasto en la otra sucursal',
        help_text='Par del reparto Colón ↔ Corrientes.',
    )
    usuario_creacion = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gastos_oficina_creados',
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Gasto de oficina'
        verbose_name_plural = 'Gastos de oficina'
        ordering = ['-fecha', '-id']

    def __str__(self):
        return f'{self.descripcion} — ${self.monto}'

    @property
    def categoria_raiz(self):
        cat = self.categoria
        while cat and cat.parent_id:
            cat = cat.parent
        return cat


def _fecha_inicio_caja_default():
    from datetime import date

    return date(2026, 6, 7)


class InicioCajaLibroPropiedad(models.Model):
    """
    Saldo de inicio de caja del libro por departamento (uno distinto por propiedad).
    Fecha por defecto 07/06/2026; editable.
    """

    propiedad = models.OneToOneField(
        'Propiedad',
        on_delete=models.CASCADE,
        related_name='inicio_caja_libro',
    )
    fecha = models.DateField(
        default=_fecha_inicio_caja_default,
        verbose_name='Fecha inicio de caja',
        help_text='Por defecto 07/06/2026.',
    )
    monto_ars = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Inicio de caja ARS',
    )
    monto_usd = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('0'),
        verbose_name='Inicio de caja USD',
    )
    actualizado_en = models.DateTimeField(auto_now=True)
    actualizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='inicios_caja_libro_actualizados',
    )

    class Meta:
        verbose_name = 'Inicio de caja libro propiedad'
        verbose_name_plural = 'Inicios de caja libro propiedad'

    def __str__(self):
        return f'Inicio caja #{self.propiedad_id} — ${self.monto_ars}'


class FilaManualLibroPropiedad(models.Model):
    """
    Anotación manual en el libro de un departamento.
    Permite cargar gastos/alquileres en ARS y USD aparte de caja.
    """

    propiedad = models.ForeignKey(
        'Propiedad',
        on_delete=models.CASCADE,
        related_name='filas_manuales_libro',
    )
    fecha = models.DateField()
    descripcion = models.CharField(max_length=255, blank=True, default='')
    gastos_ars = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0')
    )
    alquileres_ars = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0')
    )
    gastos_usd = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0')
    )
    ingreso_usd = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0')
    )
    tipo_cambio = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Tipo de cambio',
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='filas_manuales_libro_creadas',
    )

    class Meta:
        verbose_name = 'Fila manual libro propiedad'
        verbose_name_plural = 'Filas manuales libro propiedad'
        ordering = ['fecha', 'id']

    def __str__(self):
        return f'{self.fecha} — {self.descripcion or "sin desc."} (#{self.propiedad_id})'
