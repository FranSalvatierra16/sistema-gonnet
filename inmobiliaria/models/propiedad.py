from django.db import models
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from datetime import date
from django.utils.timezone import now
from django.contrib.auth.models import User

from .persona import Propietario, Inquilino, Vendedor

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
    departamento = models.IntegerField()
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

        
    # def save(self, *args, **kwargs):
    #     creating = self._state.adding
    #     super().save(*args, **kwargs)
        
    #     if creating:
    #         # Crear precios por defecto cuando la propiedad se guarda por primera vez
    #         for tipo in TipoPrecio.choices:
    #             Precio.objects.create(propiedad=self, tipo_precio=tipo[0], precio_total=0, precio_por_dia=0)
# En models.py
class ImagenPropiedad(models.Model):
    propiedad = models.ForeignKey(Propiedad, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='propiedades/')

    def __str__(self):
        return f"Imagen de {self.propiedad}"         
class Reserva(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='reservas')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    hora_ingreso = models.TimeField()  
    hora_egreso = models.TimeField()  
    fecha_creacion = models.DateTimeField(default=now)  
    vendedor = models.ForeignKey(Vendedor, on_delete=models.SET_NULL, null=True, related_name='reservas_vendedor')  
    cliente = models.ForeignKey(Inquilino, on_delete=models.SET_NULL, null=True, related_name='reservas_cliente')  
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    senia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)  # Nueva seña
    pago_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)  # Pago total
    cuota_pendiente = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)  # Nueva cuota pendiente
    estado = models.CharField(max_length=20, choices=[('en_espera', 'En Espera'), ('confirmada', 'Confirmada'), ('pagada', 'Pagada')], default='en_espera')

    def calcular_cuota_pendiente(self):
        if self.precio_total and self.pago_total:
            self.cuota_pendiente = self.precio_total - self.pago_total
            self.save()
    
    def confirmar_reserva(self, pago_senia):
        # Lógica para confirmar la reserva y registrar la seña
        self.senia = pago_senia
        self.pago_total = pago_senia  # Se inicializa con el valor de la seña
        self.estado = 'confirmada'
        self.calcular_cuota_pendiente()
        self.save()
    
    def realizar_pago(self, pago):
        # Lógica para manejar pagos adicionales
        self.pago_total += pago
        self.calcular_cuota_pendiente()
        if self.cuota_pendiente <= 0:
            self.estado = 'pagada'
        self.save()


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

class TipoPrecio(models.TextChoices):
    QUINCENA_1_ENERO = 'quincena_1_enero', _('Primera Quincena de Enero')
    QUINCENA_2_ENERO = 'quincena_2_enero', _('Segunda Quincena de Enero')
    QUINCENA_1_FEBRERO = 'quincena_1_febrero', _('Primera Quincena de Febrero')
    QUINCENA_2_FEBRERO = 'quincena_2_febrero', _('Segunda Quincena de Febrero')
    QUINCENA_1_MARZO = 'quincena_1_marzo', _('Primera Quincena de Marzo')
    QUINCENA_2_MARZO = 'quincena_2_marzo', _('Segunda Quincena de Marzo')
    FINDE_LARGO = 'finde_largo', _('Fin de Semana Largo')

class Precio(models.Model):
    propiedad = models.ForeignKey('Propiedad', on_delete=models.CASCADE, related_name='precios')
    tipo_precio = models.CharField(max_length=20, choices=TipoPrecio.choices)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # Campo opcional
    precio_por_dia = models.DecimalField(max_digits=10, decimal_places=2)
    ajuste_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Campo para ajuste en %

    class Meta:
        unique_together = ('propiedad', 'tipo_precio')

    def __str__(self):
        return f"{self.get_tipo_precio_display()} - {self.propiedad}"

    def save(self, *args, **kwargs):
        # Calcular el precio total para quincenas o fines de semana largos si no está especificado
        if 'quincena' in self.tipo_precio and not self.precio_total:
            self.precio_total = self.precio_por_dia * 15
        elif self.tipo_precio == TipoPrecio.FINDE_LARGO and not self.precio_total:
            self.precio_total = self.precio_por_dia * 4
        
        # Aplicar el ajuste en porcentaje, si existe
        if self.ajuste_porcentaje:
            ajuste = (self.ajuste_porcentaje / 100) * self.precio_total
            self.precio_total += ajuste

        super().save(*args, **kwargs)
