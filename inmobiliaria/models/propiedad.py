from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_dni(value):
    if not value.isdigit() or len(value) != 8:
        raise ValidationError(
            _('%(value)s no es un DNI válido. Debe contener 8 dígitos.'),
            params={'value': value},
        )

class Prop(models.Model):
    dni = models.CharField(max_length=8, unique=True, validators=[validate_dni])
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    email = models.EmailField()
    celular = models.CharField(max_length=20)
    observaciones = models.TextField(blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    def clean(self):
        super().clean()
        if self.celular:
            # Remove any non-digit characters
            self.celular = ''.join(filter(str.isdigit, self.celular))

class Propiedad(models.Model):
    DIRECCION_MAX_LENGTH = 255
    PRECIO_TIPO_CHOICES = [
        ('diario', 'Por día'),
        ('venta', 'Por venta'),
        ('alquiler', 'Por alquiler')
    ]
    
    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    precio_tipo = models.CharField(max_length=10, choices=PRECIO_TIPO_CHOICES)
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    descripcion = models.TextField(blank=True)
    vista = models.BooleanField(default=False)
    piso = models.IntegerField()
    ambientes = models.IntegerField()
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.direccion} - {self.precio}"
