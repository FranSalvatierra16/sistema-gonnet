from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from .persona import Propietario
TIPOS_VISTA = [
    ('a_la_ calle', 'A la calle'),
    ('contrafrente', 'Contrafrente'),
    ('lateral', 'Lateral'),
   
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
    valoracion = models.IntegerField(validators=[MinValueValidator(0), MaxValueValidator(10)]) 
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    propietario = models.ForeignKey(Propietario, on_delete=models.SET_NULL, null=True, blank=True, related_name='propiedades')
    precio_diario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por día")
    habilitar_precio_diario = models.BooleanField(default=False, verbose_name="Habilitar precio por día")

    precio_venta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por venta")
    habilitar_precio_venta = models.BooleanField(default=False, verbose_name="Habilitar precio por venta")

    precio_alquiler = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por alquiler")
    habilitar_precio_alquiler = models.BooleanField(default=False, verbose_name="Habilitar precio por alquiler")
    amoblado = models.BooleanField(default=False)
    cochera = models.BooleanField(default=False)
    tv_smart= models.BooleanField(default=False)
    wifi= models.BooleanField(default=False)
    dependencia = models.BooleanField(default=False)
    patio= models.BooleanField(default=False)
    parrilla = models.BooleanField(default=False)
    piscina = models.BooleanField(default=False)
    reciclado = models.BooleanField(default=False)
    a_estrenar = models.BooleanField(default=False)
    terraza = models.BooleanField(default=False)
    balcon = models.BooleanField(default=False)
    baulera = models.BooleanField(default=False)
    lavadero = models.BooleanField(default=False)
    seguridad = models.BooleanField(default=False)
    vista_al_Mar= models.BooleanField(default=False)
    vista_panoramica = models.BooleanField(default=False)
    apto_credito = models.BooleanField(default=False)
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

# Función para generar la ruta de almacenamiento de las imágenes
def property_image_path(instance, filename):
    return f'property_images/{instance.propiedad.id}/{filename}'

class PropiedadImagen(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='imagenes')
    imagen = models.ImageField(upload_to=property_image_path)

    def __str__(self):
        return f"Imagen de {self.propiedad.direccion}"