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

    def nombre_completo_display(self):
        """Apellido primero, luego nombre cuando hay ambos."""
        ap = (self.apellido or '').strip()
        nom = (self.nombre or '').strip()
        if ap and nom:
            return f'{ap}, {nom}'
        return ap or nom or ''

    def __str__(self):
        return self.nombre_completo_display() or super().__str__()
 
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
    (5, 'Super administrador'),
]


def usuario_es_nivel_administracion(user):
    """Nivel 4 o 5, o superusuario de Django (mismas rutas de administración que antes tenía solo el 4)."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'nivel', None) in (4, 5)


def usuario_puede_eliminar_movimiento_caja(user):
    """Super administrador (nivel 5) o superusuario Django: anula movimiento de caja y recibo asociado."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'nivel', None) == 5


def usuario_puede_editar_movimiento_caja(user):
    """Super administrador (nivel 5) o superusuario Django: corrige montos de un movimiento de caja."""
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    if getattr(user, 'is_superuser', False):
        return True
    return getattr(user, 'nivel', None) == 5


def usuario_puede_editar_nivel_vendedor(user):
    """Solo super administrador (nivel 5) o superusuario Django puede cambiar el nivel de un vendedor."""
    return usuario_puede_editar_movimiento_caja(user)


def usuario_puede_revertir_operacion_a_reserva(user):
    """Super administrador (nivel 5) o superusuario Django: devuelve operación a reserva sin seña."""
    return usuario_puede_editar_movimiento_caja(user)


def usuario_puede_anular_vale(user):
    """Administración (nivel 4+) o superusuario: elimina el vale y anula el movimiento de caja vinculado."""
    return usuario_es_nivel_administracion(user)


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
        help_text='Porcentaje sobre honorarios cuando la propiedad está marcada como primer fichaje (alquiler por día).',
    )
    comision_segundo_fichaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión segundo fichaje (%)',
        help_text='Porcentaje sobre honorarios cuando la propiedad está marcada como segundo fichaje (alquiler por día).',
    )
    comision_primer_fichaje_invierno = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión primer fichaje invierno (%)',
        help_text='Sobre honorarios en contratos/reservas invierno (9 meses). Si está vacío, usa el % de primer fichaje general.',
    )
    comision_segundo_fichaje_invierno = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión segundo fichaje invierno (%)',
        help_text='Sobre honorarios en invierno. Si está vacío, usa segundo fichaje general o primer fichaje invierno.',
    )
    comision_primer_fichaje_24_meses = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión primer fichaje 24 meses (%)',
        help_text='Sobre honorarios en contratos/reservas de 24 meses. Si está vacío, usa el % de primer fichaje general.',
    )
    comision_segundo_fichaje_24_meses = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión segundo fichaje 24 meses (%)',
        help_text='Sobre honorarios en 24 meses. Si está vacío, usa segundo fichaje general o primer fichaje 24 meses.',
    )
    comision_alquiler_24_meses = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión alquiler largo / 24 meses (%)',
        help_text='Sobre honorarios en contratos/reservas de 24 meses o largo plazo (productor).',
    )
    comision_invierno = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión alquiler invierno (%)',
        help_text='Sobre honorarios en invierno / 9 meses (productor de la operación).',
    )
    comision_invierno_propiedad_oficina = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión invierno — propiedad oficina (%)',
        help_text='Mismo criterio que invierno, pero en propiedades marcadas como «propiedad oficina».',
    )
    comision_alquiler_24_meses_propiedad_oficina = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='Comisión 24 meses — propiedad oficina (%)',
        help_text='Alquiler largo / 24 meses en propiedades marcadas como «propiedad oficina».',
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

    def nombre_completo_display(self):
        """Apellido primero, luego nombre cuando hay ambos."""
        ap = (self.apellido or '').strip()
        nom = (self.nombre or '').strip()
        if ap and nom:
            return f'{ap}, {nom}'
        return ap or nom or ''

    def __str__(self):
        nc = self.nombre_completo_display()
        return f'#{self.id} - {nc}' if nc else f'#{self.id}'

    def clean(self):
        super().clean()
        if self.celular:
            self.celular = ''.join(filter(str.isdigit, self.celular))

    def nombre_completo_vendedor(self):
        return self.nombre_completo_display()

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

    def porcentaje_fichaje_efectivo(self, tipo_fichaje=None, categoria_operacion=None):
        """% fichaje según tipo de operación; si no hay % específico, usa cualquier % de fichaje cargado."""
        from inmobiliaria.models.comision import porcentaje_fichaje_vendedor

        pct = porcentaje_fichaje_vendedor(self, tipo_fichaje, categoria_operacion)
        if pct is not None and pct > 0:
            return pct
        es_segundo = (tipo_fichaje or 'primer').strip().lower() == 'segundo'
        if es_segundo:
            orden = (
                'comision_segundo_fichaje_24_meses',
                'comision_segundo_fichaje_invierno',
                'comision_segundo_fichaje',
                'comision_primer_fichaje_24_meses',
                'comision_primer_fichaje_invierno',
                'comision_primer_fichaje',
            )
        else:
            orden = (
                'comision_primer_fichaje_24_meses',
                'comision_primer_fichaje_invierno',
                'comision_primer_fichaje',
                'comision_segundo_fichaje_24_meses',
                'comision_segundo_fichaje_invierno',
                'comision_segundo_fichaje',
            )
        for attr in orden:
            val = getattr(self, attr, None)
            if val is not None and val > 0:
                return val
        return None

    def porcentaje_comision_para_reserva(self, reserva):
        """
        % de comisión del productor para una reserva (alquiler por día).

        Las reservas no usan % invierno/24 (eso es de contratos). Se usa el %
        normal del vendedor / default de sucursal, o el de fichaje solo si
        aplica en la ficha y no hay % de operación por día (legado).
        """
        if not reserva or not getattr(reserva, 'propiedad_id', None):
            return self.porcentaje_comision_efectivo()

        prop = reserva.propiedad
        # Comisión por día (campo principal del productor).
        if self.comision is not None and self.comision > 0:
            return self.comision
        default = getattr(self.sucursal, 'porcentaje_comision_default', None)
        if default is not None and default > 0:
            return default

        tipo = getattr(prop, 'tipo_fichaje', None) or 'primer'
        if (
            tipo == 'segundo'
            and self.comision_segundo_fichaje is not None
            and self.comision_segundo_fichaje > 0
        ):
            return self.comision_segundo_fichaje
        if (
            tipo == 'primer'
            and self.comision_primer_fichaje is not None
            and self.comision_primer_fichaje > 0
        ):
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
    dni = models.CharField(max_length=8, validators=[validate_dni], blank=True, null=True)
    def nombre_completo_inquilino(self):
        return self.nombre_completo_display()
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
    dni = models.CharField(max_length=8, validators=[validate_dni], blank=True, null=True)

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
        return self.nombre_completo_display()
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
