"""Leads / consultas del portal público (opción A: no crea Reserva)."""
from django.db import models
from django.utils import timezone


class ConsultaWeb(models.Model):
    ESTADO_NUEVA = 'nueva'
    ESTADO_CONTACTADA = 'contactada'
    ESTADO_CERRADA = 'cerrada'
    ESTADO_CHOICES = [
        (ESTADO_NUEVA, 'Nueva'),
        (ESTADO_CONTACTADA, 'Contactada'),
        (ESTADO_CERRADA, 'Cerrada'),
    ]

    nombre = models.CharField(max_length=120)
    email = models.EmailField(blank=True, default='')
    telefono = models.CharField(max_length=40, blank=True, default='')
    mensaje = models.TextField(blank=True, default='')
    fecha_desde = models.DateField(null=True, blank=True)
    fecha_hasta = models.DateField(null=True, blank=True)
    propiedad = models.ForeignKey(
        'Propiedad',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consultas_web',
    )
    ficha = models.CharField(max_length=64, blank=True, default='')
    sucursal_preferida = models.CharField(max_length=80, blank=True, default='')
    ambientes = models.PositiveSmallIntegerField(null=True, blank=True)
    tipo_operacion = models.CharField(max_length=40, blank=True, default='alquiler_temporario')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default=ESTADO_NUEVA)
    creado_en = models.DateTimeField(default=timezone.now)
    notas_internas = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-creado_en']
        verbose_name = 'Consulta web'
        verbose_name_plural = 'Consultas web'

    def __str__(self):
        prop = self.propiedad_id or self.ficha or '—'
        return f'Consulta {self.nombre} · {prop} · {self.creado_en:%d/%m/%Y}'
