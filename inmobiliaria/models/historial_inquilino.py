from django.db import models
from django.utils import timezone


class HistorialInquilino(models.Model):
    """Eventos de operaciones vinculadas a un inquilino (anulaciones, cambios de precio, etc.)."""

    TIPO_CHOICES = [
        ('reserva_creada', 'Reserva creada'),
        ('operacion_anulada', 'Operación anulada'),
        ('vuelta_a_reserva', 'Vuelta a reserva pendiente'),
        ('montos_modificados', 'Montos modificados'),
        ('fechas_modificadas', 'Fechas modificadas'),
        ('estado_modificado', 'Estado modificado'),
    ]

    inquilino = models.ForeignKey(
        'Inquilino',
        on_delete=models.CASCADE,
        related_name='historial_eventos',
    )
    reserva = models.ForeignKey(
        'Reserva',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_inquilino_eventos',
    )
    contrato = models.ForeignKey(
        'ContratoAlquiler',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_inquilino_eventos',
    )
    tipo = models.CharField(max_length=32, choices=TIPO_CHOICES)
    detalle = models.TextField(blank=True)
    precio_anterior = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    precio_nuevo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    senia_anterior = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    senia_nueva = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fecha_inicio_anterior = models.DateField(null=True, blank=True)
    fecha_fin_anterior = models.DateField(null=True, blank=True)
    fecha_inicio_nueva = models.DateField(null=True, blank=True)
    fecha_fin_nueva = models.DateField(null=True, blank=True)
    estado_anterior = models.CharField(max_length=32, blank=True)
    estado_nuevo = models.CharField(max_length=32, blank=True)
    usuario = models.ForeignKey(
        'Vendedor',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='historial_inquilino_registrado',
    )
    creado = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-creado', '-id']
        indexes = [
            models.Index(fields=['inquilino', '-creado'], name='hist_inq_inq_creado_idx'),
            models.Index(fields=['reserva', '-creado'], name='hist_inq_res_creado_idx'),
        ]
        verbose_name = 'Historial de inquilino'
        verbose_name_plural = 'Historial de inquilinos'

    def __str__(self):
        return f'{self.get_tipo_display()} — inquilino {self.inquilino_id} ({self.creado:%d/%m/%Y %H:%M})'

    def get_tipo_badge_class(self):
        return {
            'reserva_creada': 'bg-primary',
            'operacion_anulada': 'bg-danger',
            'vuelta_a_reserva': 'bg-warning text-dark',
            'montos_modificados': 'bg-info text-dark',
            'fechas_modificadas': 'bg-secondary',
            'estado_modificado': 'bg-dark',
        }.get(self.tipo, 'bg-light text-dark')
