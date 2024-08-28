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

    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    descripcion = models.TextField(blank=True)
    vista = models.BooleanField(default=False)
    piso = models.IntegerField()
    ambientes = models.IntegerField()
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")

    precio_diario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por día")
    habilitar_precio_diario = models.BooleanField(default=False, verbose_name="Habilitar precio por día")

    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por venta")
    habilitar_precio_venta = models.BooleanField(default=False, verbose_name="Habilitar precio por venta")

    precio_alquiler = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por alquiler")
    habilitar_precio_alquiler = models.BooleanField(default=False, verbose_name="Habilitar precio por alquiler")

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.direccion}"

    def clean(self):
        super().clean()

        # Validar que al menos un tipo de precio esté habilitado y que el campo de precio correspondiente no esté vacío
        precios_habilitados = [
            self.habilitar_precio_diario,
            self.habilitar_precio_venta,
            self.habilitar_precio_alquiler
        ]

        if not any(precios_habilitados):
            raise ValidationError(_('Debe habilitar al menos un tipo de precio.'))

        # Validar que si un precio está habilitado, tenga un valor asignado
        if self.habilitar_precio_diario and not self.precio_diario:
            raise ValidationError(_('Debe ingresar un precio por día si está habilitado.'))

        if self.habilitar_precio_venta and not self.precio_venta:
            raise ValidationError(_('Debe ingresar un precio de venta si está habilitado.'))

        if self.habilitar_precio_alquiler and not self.precio_alquiler:
            raise ValidationError(_('Debe ingresar un precio de alquiler si está habilitado.'))