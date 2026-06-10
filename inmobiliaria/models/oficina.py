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
        help_text='Opcional: egreso de caja que pagó este gasto.',
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
