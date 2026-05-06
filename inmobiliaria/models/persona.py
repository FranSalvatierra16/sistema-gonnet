from decimal import Decimal
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
    ('cuit', 'CUIT'),
    ('le', 'LE'),
    ('ls', 'LS'),
    ('cipf', 'CIPF'),
    ('pas', 'PAS'),
]

def validate_dni(value):
    if value:  # Solo validar si hay valor (ahora es opcional)
        if not value.isdigit() or (len(value) != 7 and len(value) != 8):
            raise ValidationError(
                _('%(value)s no es un DNI válido. Debe contener 7 u 8 dígitos.'),
                params={'value': value},
            )

class Persona(models.Model):
   
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    email = models.EmailField()
    celular = models.CharField(max_length=20)
    observaciones = models.TextField(blank=True)
    localidad = models.CharField(max_length=100)  # Campo para localidad
    provincia = models.CharField(max_length=100)
    domicilio = models.CharField(max_length=100)
    codigo_postal = models.CharField(max_length=10, blank=True, null=True)  # Campo para código postal (opcional)
    cuit = models.CharField(
        max_length=11, 
        validators=[RegexValidator(regex=r'^\d{11}$', message='CUIT debe tener 11 dígitos')],
        blank=True,  # Permitir que el campo esté vacío en formularios
        null=True    # Permitir que el campo sea nulo en la base de datos
    )
    tipo_ins = models.CharField(max_length=4, choices=TIPOS_INS, default='otro', null=True, blank=True)  # Campo para tipo de inscripción
    tipo_doc = models.CharField(max_length=4, choices=TIPOS_DOC, default='otro')
    sucursal = models.ForeignKey(
        'Sucursal', 
        on_delete=models.PROTECT,
        related_name='%(class)s_set'
    )

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.apellido}, {self.nombre}" if self.apellido and self.nombre else f"{self.nombre} {self.apellido}"
 
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
    dni = models.CharField(max_length=8, blank=True, null=True)
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    fecha_nacimiento = models.DateField(null=True, blank=True)

    email = models.EmailField()
    comision = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name='Comisión por día (%)',
        help_text='Porcentaje para alquiler por día (operación estándar). Respaldo si no aplica % de fichaje, invierno ni alquiler largo / 24 meses.',
        null=True,
        blank=True,
    )
    comision_primer_fichaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión primer fichaje (%)',
        help_text='Porcentaje cuando la propiedad está marcada como primer fichaje',
    )
    comision_segundo_fichaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión segundo fichaje (%)',
        help_text='Porcentaje cuando la propiedad está marcada como segundo fichaje',
    )
    comision_alquiler_24_meses = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión alquiler largo / 24 meses (%)',
        help_text='Aplica a reservas de alquiler largo (≈20 meses o más entre inicio y fin)',
    )
    comision_invierno = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión alquiler invierno (%)',
        help_text='Si la propiedad tiene invierno habilitado, la reserva dura menos de 20 meses y el inicio cae entre abr-oct (temporada típica sur), se usa este %',
    )
    celular = models.CharField(max_length=20, blank=True)
    nivel = models.IntegerField(choices=NIVELES_VENDEDOR, default=1, help_text="Nivel del vendedor para determinar sus permisos")
    
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='vendedores')

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='vendedor_set',
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to.'
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='vendedor_set',
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.'
    )

    password_temporal = models.BooleanField(
        default=False,
        verbose_name='Contraseña temporal',
        help_text='Indica si el usuario debe cambiar su contraseña en el próximo inicio de sesión'
    )

    def __str__(self):
        return f"#{self.id} - {self.apellido}, {self.nombre}" if self.apellido and self.nombre else f"#{self.id} - {self.nombre} {self.apellido}"

    def clean(self):
        super().clean()
        if self.celular:
            self.celular = ''.join(filter(str.isdigit, self.celular))
    def nombre_completo_vendedor(self):
        return f"{self.apellido}, {self.nombre}" if self.apellido and self.nombre else f"{self.nombre} {self.apellido}"

    def porcentaje_comision_efectivo(self):
        """
        % comisión por día efectivo: el campo comisión si está definido; si no, el default de la sucursal.
        """
        if self.comision is not None:
            return self.comision
        default = getattr(self.sucursal, 'porcentaje_comision_default', None)
        if default is not None:
            return default
        return Decimal('0')

    def porcentaje_comision_para_reserva(self, reserva):
        """
        Elige el % según duración (24 meses / invierno) y tipo de fichaje de la propiedad.
        Reserva debe tener propiedad cargada (select_related recomendado en la vista).
        """
        if not reserva or not getattr(reserva, 'propiedad_id', None):
            return self.porcentaje_comision_efectivo()

        prop = reserva.propiedad
        try:
            dias = (reserva.fecha_fin - reserva.fecha_inicio).days
        except (TypeError, AttributeError):
            dias = 0

        # ~20 meses o más: se considera alquiler largo / 24 meses para comisión
        es_alquiler_largo = dias >= 600
        if es_alquiler_largo and self.comision_alquiler_24_meses is not None:
            return self.comision_alquiler_24_meses

        # Invierno / temporada fría: propiedad con alquiler invierno habilitado, no largo plazo
        if (
            self.comision_invierno is not None
            and dias < 600
            and dias >= 14
            and getattr(prop, 'habilitar_invierno', False)
        ):
            try:
                mes_ini = reserva.fecha_inicio.month
            except AttributeError:
                mes_ini = 0
            # Hemisferio sur: inicio típico temporada invierno (abr–oct)
            if mes_ini in (4, 5, 6, 7, 8, 9, 10):
                return self.comision_invierno

        tipo = getattr(prop, 'tipo_fichaje', None) or 'primer'
        if tipo == 'segundo' and self.comision_segundo_fichaje is not None:
            return self.comision_segundo_fichaje
        if tipo == 'primer' and self.comision_primer_fichaje is not None:
            return self.comision_primer_fichaje

        return self.porcentaje_comision_efectivo()

    class Meta:
        verbose_name = "Vendedor"
        verbose_name_plural = "Vendedores"
       
    def save(self, *args, **kwargs):
        if not self.pk:  # Si es una nueva instancia
            self.is_active = True  # Activar el usuario automáticamente
        
        # Intentar guardar, y si hay error de ID duplicado, arreglar la secuencia
        try:
            super().save(*args, **kwargs)
        except Exception as e:
            # Verificar si es un error de ID duplicado en PostgreSQL
            error_str = str(e)
            if 'duplicate key value violates unique constraint' in error_str and 'vendedor_pkey' in error_str:
                from django.db import connection
                from django.conf import settings
                
                # Solo intentar arreglar si estamos usando PostgreSQL
                if 'postgresql' in settings.DATABASES['default']['ENGINE']:
                    # Arreglar la secuencia automáticamente
                    with connection.cursor() as cursor:
                        # Obtener el máximo ID actual
                        cursor.execute("SELECT MAX(id) FROM inmobiliaria_vendedor;")
                        max_id = cursor.fetchone()[0] or 0
                        
                        # Obtener el nombre de la secuencia
                        cursor.execute("""
                            SELECT pg_get_serial_sequence('inmobiliaria_vendedor', 'id');
                        """)
                        sequence_result = cursor.fetchone()
                        
                        if sequence_result and sequence_result[0]:
                            sequence_name = sequence_result[0]
                            # Establecer la secuencia al máximo ID + 1
                            cursor.execute(f"SELECT setval('{sequence_name}', {max_id}, true);")
                            
                            # Intentar guardar de nuevo
                            super().save(*args, **kwargs)
                        else:
                            # Si no se puede obtener la secuencia, re-lanzar el error original
                            raise
                else:
                    # Si no es PostgreSQL, re-lanzar el error original
                    raise
            else:
                # Si no es un error de ID duplicado, re-lanzar el error original
                raise

class Inquilino(Persona):
    garantia = models.TextField(blank=True, help_text="Información sobre la garantía del inquilino")
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='inquilinos')
    dni = models.CharField(max_length=8, unique=True, validators=[validate_dni], blank=True, null=True)
    def nombre_completo_inquilino(self):
        return f"{self.apellido}, {self.nombre}" if self.apellido and self.nombre else f"{self.nombre} {self.apellido}"
    class Meta:
        verbose_name = "Inquilino"
        verbose_name_plural = "Inquilinos"

class Propietario(Persona):
    cuenta_bancaria = models.CharField(
        max_length=500,
        blank=True,
        help_text="Resumen automático (banco, titular, CBU/alias, cuenta) para listados e integraciones",
    )
    cuenta_banco = models.CharField(
        max_length=100,
        blank=True,
        help_text="Nombre del banco o billetera",
    )
    cuenta_titular = models.CharField(
        max_length=200,
        blank=True,
        help_text="Titular de la cuenta",
    )
    cuenta_cbu_alias = models.CharField(
        max_length=100,
        blank=True,
        help_text="CBU, CVU o alias para transferencias",
    )
    cuenta_numero = models.CharField(
        max_length=50,
        blank=True,
        help_text="Número de cuenta (opcional, referencia)",
    )
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='propietarios')
    dni = models.CharField(max_length=8, unique=True, validators=[validate_dni], blank=True, null=True)

    def _actualizar_resumen_cuenta_bancaria(self):
        parts = []
        b = (self.cuenta_banco or '').strip()
        t = (self.cuenta_titular or '').strip()
        c = (self.cuenta_cbu_alias or '').strip()
        n = (self.cuenta_numero or '').strip()
        if b:
            parts.append(f'Banco: {b}')
        if t:
            parts.append(f'Titular: {t}')
        if c:
            parts.append(f'CBU/Alias: {c}')
        if n:
            parts.append(f'Cuenta: {n}')
        self.cuenta_bancaria = ' · '.join(parts)[:500]

    def save(self, *args, **kwargs):
        self._actualizar_resumen_cuenta_bancaria()
        super().save(*args, **kwargs)

    def nombre_completo_propietario(self):
        return f"{self.apellido}, {self.nombre}" if self.apellido and self.nombre else f"{self.nombre} {self.apellido}"
    class Meta:
        verbose_name = "Propietario"
        verbose_name_plural = "Propietarios"

class User(AbstractUser):
    groups = models.ManyToManyField(
        'auth.Group',
        related_name='custom_user_set',
        blank=True,
        verbose_name='groups',
        help_text='The groups this user belongs to.'
    )
    
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='custom_user_set',
        blank=True,
        verbose_name='user permissions',
        help_text='Specific permissions for this user.'
    )
    
    password_temporal = models.BooleanField(default=False)
    # ... otros campos ...
