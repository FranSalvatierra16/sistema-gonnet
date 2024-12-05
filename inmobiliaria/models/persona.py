from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractUser
from .sucursal import Sucursal
TIPOS_INS = [
    ('csfl', 'CSFL'),
    ('exen', 'EXEN'),
    ('rins', 'RINS'),
    ('rnin', 'RNIN'),
    ('otro', 'Otro'),
]

TIPOS_DOC = [
    ('dni', 'DNI'),
    ('le', 'LE'),
    ('ls', 'LS'),
    ('cipf', 'CIPF'),
    ('pas', 'PAS'),
]

def validate_dni(value):
    if not value.isdigit() or len(value) != 8:
        raise ValidationError(
            _('%(value)s no es un DNI válido. Debe contener 8 dígitos.'),
            params={'value': value},
        )

class Persona(models.Model):
   
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField()
    email = models.EmailField()
    celular = models.CharField(max_length=20)
    observaciones = models.TextField(blank=True)
    localidad = models.CharField(max_length=100)  # Campo para localidad
    provincia = models.CharField(max_length=100)
    domicilio = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=10)  # Campo para código postal
    cuit = models.CharField(
        max_length=11, 
        validators=[RegexValidator(regex=r'^\d{11}$', message='CUIT debe tener 11 dígitos')],
        blank=True,  # Permitir que el campo esté vacío en formularios
        null=True    # Permitir que el campo sea nulo en la base de datos
    )
    tipo_ins = models.CharField(max_length=4, choices=TIPOS_INS, default='otro')  # Campo para tipo de inscripción
    tipo_doc = models.CharField(max_length=4, choices=TIPOS_DOC, default='otro')
    sucursal = models.ForeignKey(
        'Sucursal', 
        on_delete=models.PROTECT,
        related_name='%(class)s_set'
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.nombre} {self.apellido}"
 
    def clean(self):
        super().clean()
        if self.celular:
            # Remove any non-digit characters
            self.celular = ''.join(filter(str.isdigit, self.celular))

# Definición de los niveles de vendedor
NIVELES_VENDEDOR = [
    (1, 'Básico'),
    (2, 'Intermedio'),
    (3, 'Avanzado'),
    (4, 'Administrador'),
]

class Vendedor(AbstractUser):
    dni = models.CharField(max_length=8)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    email = models.EmailField()
    comision = models.DecimalField(max_digits=5, decimal_places=2, help_text="Comisión en porcentaje", null=True, blank=True)
    celular = models.CharField(max_length=20, blank=True)
    nivel = models.IntegerField(choices=NIVELES_VENDEDOR, default=1, help_text="Nivel del vendedor para determinar sus permisos")
    
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='vendedores')

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    def clean(self):
        super().clean()
        if self.celular:
            self.celular = ''.join(filter(str.isdigit, self.celular))
    def nombre_completo_vendedor(self):
        return f"{self.nombre} {self.apellido}"
    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
       
    def save(self, *args, **kwargs):
        if not self.pk:  # Si es una nueva instancia
            self.is_active = True  # Activar el usuario automáticamente
        super().save(*args, **kwargs)

class Inquilino(Persona):
    garantia = models.TextField(blank=True, help_text="Información sobre la garantía del inquilino")
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='inquilinos')
    dni = models.CharField(max_length=8, unique=True, validators=[validate_dni])
    def nombre_completo_inquilino(self):
        return f"{self.nombre} {self.apellido}"
    class Meta:
        verbose_name = "Inquilino"
        verbose_name_plural = "Inquilinos"

class Propietario(Persona):
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='propietarios')
    dni = models.CharField(max_length=8, unique=True, validators=[validate_dni])
    def nombre_completo_propietario(self):
        return f"{self.nombre} {self.apellido}"
    class Meta:
        verbose_name = "Propietario"
        verbose_name_plural = "Propietarios"
