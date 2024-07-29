# File: inmobiliaria/models/persona.py

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_dni(value):
    if not value.isdigit() or len(value) != 8:
        raise ValidationError(
            _('%(value)s no es un DNI válido. Debe contener 8 dígitos.'),
            params={'value': value},
        )

class Persona(models.Model):
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

class Vendedor(Persona):
    comision = models.DecimalField(max_digits=5, decimal_places=2, help_text="Comisión en porcentaje")

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"

class Inquilino(Persona):
    garantia = models.TextField(blank=True, help_text="Información sobre la garantía del inquilino")

    class Meta:
        verbose_name = "Inquilino"
        verbose_name_plural = "Inquilinos"

class Propietario(Persona):
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")

    class Meta:
        verbose_name = "Propietario"
        verbose_name_plural = "Propietarios"