from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class CarteraPropiedadUsuario(models.Model):
    """Propiedad seguida por un usuario con % de participación en ganancias y gastos."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cartera_propiedades',
    )
    propiedad = models.ForeignKey(
        'Propiedad',
        on_delete=models.CASCADE,
        related_name='en_carteras_usuario',
    )
    propietario = models.ForeignKey(
        'Propietario',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='carteras_por_propietario',
        help_text='Propietario usado al agregar la propiedad (referencia).',
    )
    porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('100'),
        validators=[MinValueValidator(Decimal('0.01')), MaxValueValidator(Decimal('100'))],
        help_text='Porcentaje de ganancias y gastos de oficina que te corresponden.',
    )
    fecha_alta = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'inmobiliaria_cartera_propiedad_usuario'
        verbose_name = 'Propiedad en mi cartera'
        verbose_name_plural = 'Mis propiedades'
        constraints = [
            models.UniqueConstraint(
                fields=('usuario', 'propiedad'),
                name='uniq_cartera_usuario_propiedad',
            ),
        ]
        ordering = ['-fecha_alta']

    def __str__(self):
        return f'{self.usuario} — {self.propiedad_id} ({self.porcentaje}%)'
