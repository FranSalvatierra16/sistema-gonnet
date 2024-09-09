from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from datetime import date

from .persona import Propietario

# Definiciones de tipos de vista, valoración e inmuebles
TIPOS_VISTA = [
    ('a_la_calle', 'A la calle'),
    ('contrafrente', 'Contrafrente'),
    ('lateral', 'Lateral'),
]

TIPOS_VALORACION = [
    ('excelente', 'Excelente'),
    ('muy_bueno', 'Muy bueno'),
    ('bueno', 'Bueno'),
    ('regular', 'Regular'),
    ('malo', 'Malo'),
]

TIPOS_INMUEBLES = [
    ('-', '-'),
    ('campo', 'Campo'),
    ('casa-chalet', 'Casa - Chalet'),
    ('departamento', 'Departamento'),
    ('fondo_de_comercio', 'Fondo de Comercio'),
    ('galpon', 'Galpon'),
    ('hotel', 'Hotel'),
    ('local', 'Local'),
    ('oficina', 'Oficina'),
    ('ph', 'PH'),
    ('quinta', 'Quinta'),
    ('terreno', 'Terreno'),
    ('cochera', 'Cochera'),
    ('edificio', 'Edificio'),
    ('inmueble_en_block', 'Inmueble en Block'),
    ('duplex', 'Dúplex'),
    ('emprendimiento', 'Emprendimiento'),
    ('cabaña', 'Cabaña'), 
    ('casaquinta', 'Casa Quinta'),
    ('deposito', 'Deposito'), 
]


class Propiedad(models.Model):
    DIRECCION_MAX_LENGTH = 255

    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    descripcion = models.TextField(blank=True)
    tipo_inmueble = models.CharField(max_length=20, choices=TIPOS_INMUEBLES, default='otro')
    vista = models.CharField(max_length=20, choices=TIPOS_VISTA, default='otro')
    piso = models.IntegerField()
    ambientes = models.IntegerField()
    valoracion = models.CharField(max_length=20, choices=TIPOS_VALORACION, default='otro')
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    propietario = models.ForeignKey(Propietario, on_delete=models.SET_NULL, null=True, blank=True, related_name='propiedades')
    precio_diario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por día")
    habilitar_precio_diario = models.BooleanField(default=False, verbose_name="Habilitar precio por día")
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por venta")
    habilitar_precio_venta = models.BooleanField(default=False, verbose_name="Habilitar precio por venta")
    precio_alquiler = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por alquiler")
    habilitar_precio_alquiler = models.BooleanField(default=False, verbose_name="Habilitar precio por alquiler")
    
    # Atributos adicionales
    amoblado = models.BooleanField(default=False)
    cochera = models.BooleanField(default=False)
    tv_smart= models.BooleanField(default=False)
    wifi= models.BooleanField(default=False)
    dependencia = models.BooleanField(default=False)
    patio = models.BooleanField(default=False)
    parrilla = models.BooleanField(default=False)
    piscina = models.BooleanField(default=False)
    reciclado = models.BooleanField(default=False)
    a_estrenar = models.BooleanField(default=False)
    terraza = models.BooleanField(default=False)
    balcon = models.BooleanField(default=False)
    baulera = models.BooleanField(default=False)
    lavadero = models.BooleanField(default=False)
    seguridad = models.BooleanField(default=False)
    vista_al_Mar = models.BooleanField(default=False)
    vista_panoramica = models.BooleanField(default=False)
    apto_credito = models.BooleanField(default=False)
    
 

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.direccion}"

    def esta_disponible_en_fecha(self, fecha_inicio, fecha_fin):
        """Verifica si una propiedad está disponible entre las fechas dadas."""
        disponibilidades = self.disponibilidades.filter(
            fecha_inicio__lte=fecha_fin, 
            fecha_fin__gte=fecha_inicio
        )
        return disponibilidades.exists()

    def clean(self):
        super().clean()

        precios_habilitados = [
            self.habilitar_precio_diario,
            self.habilitar_precio_venta,
            self.habilitar_precio_alquiler
        ]

        if not any(precios_habilitados):
            raise ValidationError(_('Debe habilitar al menos un tipo de precio.'))

        if self.habilitar_precio_diario and not self.precio_diario:
            raise ValidationError(_('Debe ingresar un precio por día si está habilitado.'))

        if self.habilitar_precio_venta and not self.precio_venta:
            raise ValidationError(_('Debe ingresar un precio de venta si está habilitado.'))

        if self.habilitar_precio_alquiler and not self.precio_alquiler:
            raise ValidationError(_('Debe ingresar un precio de alquiler si está habilitado.'))
class Reserva(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='reservas')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    def clean(self):
        super().clean()

        if not self.propiedad_id:
            raise ValidationError('Debe seleccionar una propiedad para la reserva.')

        hoy = date.today()
        # Puedes añadir más lógica aquí si es necesario


class Disponibilidad(models.Model):
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE, related_name='disponibilidades')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()

    class Meta:
        verbose_name = _("Disponibilidad")
        verbose_name_plural = _("Disponibilidades")

    def clean(self):
        super().clean()

        if self.fecha_inicio and self.fecha_fin:
            if self.fecha_inicio >= self.fecha_fin:
                raise ValidationError(_("La fecha de inicio debe ser anterior a la fecha de fin."))

            if self.propiedad:
                # Check for overlapping reservations
                reservas_existentes = self.propiedad.reservas.filter(
                    Q(fecha_inicio__lte=self.fecha_fin) & Q(fecha_fin__gte=self.fecha_inicio)
                )
                if reservas_existentes.exists():
                    raise ValidationError(_('Las fechas seleccionadas se superponen con una reserva existente.'))

                # Check for overlapping availabilities
                disponibilidades_existentes = self.propiedad.disponibilidades.filter(
                    Q(fecha_inicio__lte=self.fecha_fin) & Q(fecha_fin__gte=self.fecha_inicio)
                ).exclude(pk=self.pk)
                if disponibilidades_existentes.exists():
                    raise ValidationError(_('Las fechas seleccionadas se superponen con otra disponibilidad.'))

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Disponibilidad desde {self.fecha_inicio} hasta {self.fecha_fin} para {self.propiedad}"