from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Q
from django.utils.timezone import now

import datetime
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
    ('campo', 'Campo'),
    ('casa-chalet', 'Casa - Chalet'),
    ('departamento', 'Departamento'),
    ('fondo_de_comercio', 'Fondo de Comercio'),
    ('galpon', 'Galpón'),
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
    ('deposito', 'Depósito'), 
]


class Propiedad(models.Model):
    DIRECCION_MAX_LENGTH = 255
    DEPARTAMENTO_CHOICES = [(chr(i), chr(i)) for i in range(ord('A'), ord('Z')+1)]
    direccion = models.CharField(max_length=DIRECCION_MAX_LENGTH)
    descripcion = models.TextField(blank=True)
    tipo_inmueble = models.CharField(max_length=20, choices=TIPOS_INMUEBLES, default='departamento')
    vista = models.CharField(max_length=20, choices=TIPOS_VISTA, default='a_la_calle')
    piso = models.IntegerField()
    departamento = models.CharField(max_length=1, choices=DEPARTAMENTO_CHOICES)
    ambientes = models.IntegerField()
    valoracion = models.CharField(max_length=20, choices=TIPOS_VALORACION, default='bueno')
    cuenta_bancaria = models.CharField(max_length=100, blank=True, help_text="Número de cuenta bancaria para depósitos")
    propietario = models.ForeignKey(Propietario, on_delete=models.CASCADE, related_name='propiedades')  # Cambiado a obligatorio
    
    # Resto del código permanece igual
    
    # precio_diario = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por día")
    # habilitar_precio_diario = models.BooleanField(default=False, verbose_name="Habilitar precio por día")
    # precio_venta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por venta")
    # habilitar_precio_venta = models.BooleanField(default=False, verbose_name="Habilitar precio por venta")
    # precio_alquiler = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True, verbose_name="Precio por alquiler")
    # habilitar_precio_alquiler = models.BooleanField(default=False, verbose_name="Habilitar precio por alquiler")

    # Atributos adicionales
    amoblado = models.BooleanField(default=False)
    cochera = models.BooleanField(default=False)
    tv_smart = models.BooleanField(default=False)
    wifi = models.BooleanField(default=False)
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
        if not fecha_inicio or not fecha_fin:
            # Si alguna de las fechas no está definida, considera la propiedad como disponible
            return True

        disponibilidades = self.disponibilidades.filter(
            fecha_inicio__lte=fecha_fin, 
            fecha_fin__gte=fecha_inicio
        )
        return not disponibilidades.exists()

    # def clean(self):
    #     super().clean()

    #     precios_habilitados = [
    #         self.habilitar_precio_diario,
    #         self.habilitar_precio_venta,
    #         self.habilitar_precio_alquiler
    #     ]

    #     if not any(precios_habilitados):
    #         raise ValidationError(_('Debe habilitar al menos un tipo de precio.'))

    #     if self.habilitar_precio_diario and not self.precio_diario:
    #         raise ValidationError(_('Debe ingresar un precio por día si está habilitado.'))

    #     if self.habilitar_precio_venta and not self.precio_venta:
    #         raise ValidationError(_('Debe ingresar un precio de venta si está habilitado.'))

    #     if self.habilitar_precio_alquiler and not self.precio_alquiler:
    #         raise ValidationError(_('Debe ingresar un precio de alquiler si está habilitado.'))

    def save(self, *args, **kwargs):
        creating = self._state.adding  # Detectar si es una creación
        super().save(*args, **kwargs)
    
        if creating:
            self.crear_precios_iniciales()

    @transaction.atomic
    def crear_precios_iniciales(self):
        tipos_de_precios = [
            TipoPrecio.QUINCENA_1_ENERO, TipoPrecio.QUINCENA_2_ENERO,
            TipoPrecio.QUINCENA_1_FEBRERO, TipoPrecio.QUINCENA_2_FEBRERO,
            TipoPrecio.QUINCENA_1_MARZO, TipoPrecio.QUINCENA_2_MARZO,
            TipoPrecio.FINDE_LARGO
        ]
        for tipo in tipos_de_precios:
            Precio.objects.get_or_create(
                propiedad=self,
                tipo_precio=tipo,
                defaults={'precio_total': 0, 'precio_por_dia': 0, 'ajuste_porcentaje':0}
            )
  

    class Meta:
        verbose_name = "Propiedad"
        verbose_name_plural = "Propiedades"

    def __str__(self):
        return f"{self.direccion}"        


class ImagenPropiedad(models.Model):
    propiedad = models.ForeignKey(Propiedad, related_name='imagenes', on_delete=models.CASCADE)
    imagen = models.ImageField(upload_to='propiedades/')

    def __str__(self):
        return f"Imagen de {self.propiedad}"


class Reserva(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='reservas')
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    hora_ingreso = models.TimeField(default=datetime.time(15, 0))  # Valor por defecto: 15:00
    hora_egreso = models.TimeField(default=datetime.time(10, 0))   # Valor por defecto: 10:00
    fecha_creacion = models.DateTimeField(default=now)  
    vendedor = models.ForeignKey(Vendedor, on_delete=models.SET_NULL, null=True, related_name='reservas_vendedor')  
    cliente = models.ForeignKey(Inquilino, on_delete=models.SET_NULL, null=True, related_name='reservas_cliente')  
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True) 
    senia = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    pago_total = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    cuota_pendiente = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, default=0)
    estado = models.CharField(max_length=20, choices=[('en_espera', 'En Espera'), ('confirmada', 'Confirmada'), ('pagada', 'Pagada')], default='en_espera')

    def calcular_cuota_pendiente(self):
        if self.precio_total and self.pago_total:
            self.cuota_pendiente = self.precio_total - self.pago_total
            self.save()

    def confirmar_reserva(self, pago_senia):
        self.senia = pago_senia
        self.pago_total = pago_senia
        self.estado = 'confirmada'
        self.calcular_cuota_pendiente()
        self.save()

    def realizar_pago(self, pago):
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

        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))

        if self.fecha_inicio and self.fecha_fin:
            if not self.propiedad.esta_disponible_en_fecha(self.fecha_inicio, self.fecha_fin):
                raise ValidationError(_('La propiedad no está disponible para las fechas seleccionadas.'))
        else:
            # No verificamos disponibilidad si alguna de las fechas no está definida
            pass

class TipoPrecio(models.TextChoices):
    QUINCENA_1_ENERO = 'QUINCENA_1_ENERO', _('1ra quincena Enero')
    QUINCENA_2_ENERO = 'QUINCENA_2_ENERO', _('2da quincena Enero')
    QUINCENA_1_FEBRERO = 'QUINCENA_1_FEBRERO', _('1ra quincena Febrero')
    QUINCENA_2_FEBRERO = 'QUINCENA_2_FEBRERO', _('2da quincena Febrero')
    QUINCENA_1_MARZO = 'QUINCENA_1_MARZO', _('1ra quincena Marzo')
    QUINCENA_2_MARZO = 'QUINCENA_2_MARZO', _('2da quincena Marzo')
    FINDE_LARGO = 'FINDE_LARGO', _('Finde largo')
    DICIEMBRE = 'DICIEMBRE', _('Diciembre')
    ENERO = 'ENERO', _('Enero')
    FEBRERO = 'FEBRERO', _('Febrero')
    MARZO = 'MARZO', _('Marzo')

class Precio(models.Model):
    propiedad = models.ForeignKey(Propiedad, on_delete=models.CASCADE, related_name='precios')
    tipo_precio = models.CharField(max_length=20, choices=TipoPrecio.choices)
    precio_total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    precio_por_dia = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    ajuste_porcentaje = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # Descuento en porcentaje

    class Meta:
        unique_together = ('propiedad', 'tipo_precio')

    def calcular_precio_total(self, fecha_inicio, fecha_fin):
        dias = (fecha_fin - fecha_inicio).days + 1
        mes = fecha_inicio.month

        if 'QUINCENA' in self.tipo_precio:
            base_price = self.precio_por_dia * 15  # Quincena como 15 días
            if mes == 1:  # Enero
                base_price *= 16  # Multiplicar por 16 en enero
            elif mes == 2:  # Febrero
                base_price *= 15  # Multiplicar por 15 en febrero
        elif self.tipo_precio == 'FINDE_LARGO':
            base_price = self.precio_por_dia * 4  # Finde largo como 4 días
        else:
            base_price = self.precio_por_dia * dias

        # Aplicar ajuste porcentual si se ha establecido
        if self.ajuste_porcentaje != 0:
            base_price *= (1 - self.ajuste_porcentaje / 100)

        return round(base_price, 2)

    def save(self, *args, **kwargs):
        if self.precio_por_dia is not None:
            # Calcular el precio total basado en el tipo de precio
            if 'QUINCENA' in self.tipo_precio:
                base_price = self.precio_por_dia * 15
            elif self.tipo_precio == 'FINDE_LARGO':
                base_price = self.precio_por_dia * 4
            else:
                base_price = self.precio_por_dia

            # Aplicar ajuste porcentual si se ha establecido
            if self.ajuste_porcentaje != 0:
                base_price *= (1 - self.ajuste_porcentaje / 100)

            self.precio_total = base_price

        super().save(*args, **kwargs)



