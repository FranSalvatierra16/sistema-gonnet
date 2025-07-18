from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import (
    Vendedor, 
    Inquilino, 
    Propietario, 
    Propiedad, 
    Reserva, 
    Disponibilidad, 
    ImagenPropiedad, 
    Precio,
    TipoPrecio,
    TIPOS_INMUEBLES, 
    TIPOS_VISTA, 
    TIPOS_VALORACION, 
    Sucursal, 
    VentaPropiedad, 
    MovimientoCaja, 
    Concepto, 
    BancoTarjeta,
    Registro
)
from datetime import datetime
from django.forms import modelformset_factory
from django.core.exceptions import ValidationError
from django.db import models
import os
# Formulario de creación de Vendedor
class VendedorUserCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, help_text='Requerido. 150 caracteres o menos.')
    password1 = forms.CharField(widget=forms.PasswordInput, help_text='Requerido.')
    password2 = forms.CharField(widget=forms.PasswordInput, help_text='Ingrese la misma contraseña para verificar.')

    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.all(),
        required=True,
        help_text='Seleccione la sucursal a la que pertenece el vendedor.'
    )

    class Meta:
        model = Vendedor
        fields = ['dni', 'username', 'nombre', 'apellido', 'email', 'comision', 'fecha_nacimiento', 'nivel', 'sucursal']

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        print(password1)
        password2 = self.cleaned_data.get("password2")
        print(password2)
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return password2

    def save(self, commit=True):
        vendedor = super().save(commit=False)
        vendedor.set_password(self.cleaned_data["password1"])  # Establecer la contraseña
        if commit:
            vendedor.save()
        return vendedor
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sucursal'].required = True

# Formulario de cambio de Vendedor
class VendedorChangeForm(UserChangeForm):
    class Meta:
        model = Vendedor
        fields = ['username', 'dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'comision', 'celular', 'nivel']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
        }

# Formulario de Inquilino
class InquilinoForm(forms.ModelForm):
    class Meta:
        model = Inquilino
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 'domicilio', 'codigo_postal', 'observaciones', 'garantia']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(InquilinoForm, self).__init__(*args, **kwargs)
        self.fields['cuit'].required = False

    def save(self, commit=True):
        inquilino = super(InquilinoForm, self).save(commit=False)
        if self.user:
            inquilino.sucursal = self.user.sucursal  # Asigna la sucursal del vendedor
        if commit:
            inquilino.save()
        return inquilino

# Formulario de Propietario
class PropietarioForm(forms.ModelForm):
    class Meta:
        model = Propietario
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 
                 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 
                 'domicilio', 'codigo_postal', 'observaciones', 'cuenta_bancaria']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            'cuenta_bancaria': forms.TextInput(attrs={
                'placeholder': 'Ingrese CBU o número de cuenta bancaria',
                'class': 'form-control'
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(PropietarioForm, self).__init__(*args, **kwargs)
        
        # Marcar campos requeridos
        self.fields['nombre'].required = True
        self.fields['apellido'].required = True
        self.fields['dni'].required = True
        self.fields['cuit'].required = False
        self.fields['cuenta_bancaria'].required = False
        
        # Agregar ayuda para cuenta bancaria
        self.fields['cuenta_bancaria'].help_text = 'Número de cuenta bancaria para depósitos'
        
        # Agregar clases de Bootstrap
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control'
            })

    def clean(self):
        cleaned_data = super().clean()
        dni = cleaned_data.get('dni')
        
        # Validar DNI único
        if dni and Propietario.objects.filter(dni=dni).exists():
            if not self.instance.pk or (self.instance.pk and str(self.instance.dni) != str(dni)):
                raise ValidationError({'dni': 'Ya existe un propietario con este DNI'})
        
        return cleaned_data

    def save(self, commit=True):
        propietario = super(PropietarioForm, self).save(commit=False)
        
        if self.user:
            propietario.sucursal = self.user.sucursal  # Asigna la sucursal del vendedor
        if commit:
            propietario.save()
        return propietario
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result
# Formulario de Propiedad
class PropiedadForm(forms.ModelForm):
    imagenes = MultipleFileField(
        required=False,
        help_text="Seleccione una o más imágenes para la propiedad"
    )
    propietario = forms.ModelChoiceField(
        queryset=Propietario.objects.all(),
        widget=forms.Select(attrs={'class': 'select2-propietario'}),
        required=False
    )
    id = forms.IntegerField(
        label='ID de la Propiedad',
        required=True,
        help_text='Ingrese el ID deseado para la propiedad'
    )
    llave = forms.IntegerField(
        required=False,
        label='Número de llave',
        help_text='Ingrese el número de llave de la propiedad',
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    piso = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: PB, 1, 15'
        })
    )
    departamento = forms.CharField(
        max_length=10,
        required=True,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: 1A, 150, B3'
        })
    )

    class Meta:
        model = Propiedad
        exclude = ("numero_por_propietario",)
        fields = [
            'id', 'llave', 'direccion', 'ubicacion', 'tipo_inmueble', 'vista', 'piso', 'departamento', 'ambientes', 'valoracion', 'cuenta_bancaria',

            # 'habilitar_precio_diario', 'precio_diario', 'habilitar_precio_venta', 'precio_venta',
            # 'habilitar_precio_alquiler', 'precio_alquiler',
            'amoblado', 'cochera', 'tv_smart', 'wifi', 
            'dependencia', 'patio', 'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon', 
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito', 'descripcion', 
            'propietario'
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 5}),
            'valoracion': forms.Select(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Ingrese la dirección'}),
            'ubicacion': forms.TextInput(attrs={'placeholder': 'Ingrese la ubicación'}),
            # 'precio_venta': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de venta'}),
            # 'precio_alquiler': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de alquiler'}),
            # 'precio_diario': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio diario'}),
        }
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(PropiedadForm, self).__init__(*args, **kwargs)

    def save(self, commit=True):
        propiedad = super(PropiedadForm, self).save(commit=False)
        if self.user and hasattr(self.user, 'sucursal'):
            propiedad.sucursal = self.user.sucursal  # Asigna la sucursal del vendedor
        if commit:
            propiedad.save()
            # Guardar imágenes solo si existen
            imagenes = self.cleaned_data.get('imagenes')
            if imagenes:
                # Obtener el último orden existente
                ultimo_orden = ImagenPropiedad.objects.filter(propiedad=propiedad).aggregate(
                    max_orden=models.Max('orden')
                )['max_orden'] or 0
                
                # Obtener nombres de archivos existentes para evitar duplicados
                imagenes_existentes = ImagenPropiedad.objects.filter(propiedad=propiedad)
                nombres_existentes = {os.path.basename(img.imagen.name) for img in imagenes_existentes}
                
                # Agregar las nuevas imágenes al final, evitando duplicados
                nuevas_agregadas = 0
                for imagen in imagenes:
                    nombre_archivo = os.path.basename(imagen.name)
                    # Si la imagen ya existe, saltarla
                    if nombre_archivo in nombres_existentes:
                        continue
                        
                    nuevas_agregadas += 1
                    ImagenPropiedad.objects.create(
                        propiedad=propiedad,
                        imagen=imagen,
                        orden=ultimo_orden + nuevas_agregadas
                    )
                    nombres_existentes.add(nombre_archivo)
        return propiedad
class PrecioForm(forms.ModelForm):
    class Meta:
        model = Precio
        fields = ['tipo_precio','precio_toma', 'precio_dia_toma', 'precio_por_dia', 'precio_total', 'ajuste_porcentaje']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer que precio_total sea opcional solo si ya tiene un valor
        self.fields['precio_total'].required = False

    def clean_ajuste_porcentaje(self):
        ajuste = self.cleaned_data.get('ajuste_porcentaje')
        if ajuste < -100 or ajuste > 100:
            raise forms.ValidationError("El ajuste debe estar entre -100% y 100%.")
        return ajuste

    def clean(self):
        cleaned_data = super().clean()
        # Validar que si precio_total es ingresado, no se recalcula
        precio_total = cleaned_data.get('precio_total')
        if precio_total and precio_total <= 0:
            raise forms.ValidationError("El precio total debe ser positivo.")


    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.fields['imagenes'].widget.attrs.update({'class': 'form-control-file'})


# Formulario de Imágenes de Propiedad
# class PropiedadImagenForm(forms.ModelForm):
#     class Meta:
#         model = PropiedadImagen
#         fields = ['imagen']

# Formulario de Reserva
# inmobiliaria/forms.py

# forms.py

class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ['propiedad', 'fecha_inicio', 'fecha_fin', 'vendedor', 'cliente']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}),

        }
class BuscarPropiedadesForm(forms.Form):
    origen = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ciudad de origen'
        })
    )
    destino = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ciudad de destino'
        })
    )
    fecha_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    fecha_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    tipo_inmueble = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_INMUEBLES, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    vista = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_VISTA, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    ambientes = forms.ChoiceField(
        required=True,
        choices=[
            ('1', '1 Ambiente'),
            ('2', '2 Ambientes'),
            ('3', '3 Ambientes'),
            ('4', '4 Ambientes'),
            ('5', '5 o más Ambientes'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    ver_todas = forms.BooleanField(
        required=False, 
        label="Ver todas las propiedades", 
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    valoracion = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_VALORACION, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    precio_min = forms.DecimalField(required=False, min_value=0)
    precio_max = forms.DecimalField(required=False, min_value=0)

    # Características booleanas
    amoblado = forms.BooleanField(required=False)
    cochera = forms.BooleanField(required=False)
    tv_smart = forms.BooleanField(required=False)
    wifi = forms.BooleanField(required=False)
    dependencia = forms.BooleanField(required=False)
    patio = forms.BooleanField(required=False)
    parrilla = forms.BooleanField(required=False)
    piscina = forms.BooleanField(required=False)
    reciclado = forms.BooleanField(required=False)
    a_estrenar = forms.BooleanField(required=False)
    terraza = forms.BooleanField(required=False)
    balcon = forms.BooleanField(required=False)
    baulera = forms.BooleanField(required=False)
    lavadero = forms.BooleanField(required=False)
    seguridad = forms.BooleanField(required=False)
    vista_al_Mar = forms.BooleanField(required=False)
    vista_panoramica = forms.BooleanField(required=False)
    apto_credito = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        
        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise forms.ValidationError("La fecha de inicio no puede ser posterior a la fecha de fin.")
        
        return cleaned_data

class DisponibilidadForm(forms.ModelForm):
    class Meta:
        model = Disponibilidad
        fields = ['fecha_inicio', 'fecha_fin']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        }

    def __init__(self, propiedad=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.propiedad = propiedad

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')

        if fecha_inicio and fecha_fin:
            if fecha_fin < fecha_inicio:
                raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio')

            if self.propiedad:
                # Verificar solapamiento solo con fechas que se superponen
                solapamiento = Disponibilidad.objects.filter(
                    propiedad=self.propiedad,
                    fecha_fin__gte=fecha_inicio,
                    fecha_inicio__lte=fecha_fin
                )
                
                # Si estamos editando, excluir la disponibilidad actual
                if self.instance.pk:
                    solapamiento = solapamiento.exclude(pk=self.instance.pk)
                
                if solapamiento.exists():
                    fechas_ocupadas = [
                        f"({d.fecha_inicio.strftime('%d/%m/%Y')} - {d.fecha_fin.strftime('%d/%m/%Y')})"
                        for d in solapamiento
                    ]
                    raise ValidationError(
                        f'Las fechas se solapan con disponibilidades existentes: {", ".join(fechas_ocupadas)}'
                    )

        return cleaned_data

PrecioFormSet = modelformset_factory(
    Precio,
    form=PrecioForm,
    extra=0,  # No agrega formularios extra por defecto
    can_delete=True  # Para poder eliminar precios
)
class PropietarioBuscarForm(forms.Form):
    termino = forms.CharField(required=False, label='Buscar por nombre completo o DNI')

class InquilinoBuscarForm(forms.Form):
    termino = forms.CharField(required=False, label='Buscar nombre completo o DNI')

class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = ['nombre', 'direccion', 'telefono', 'email']
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la sucursal'
            }),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Dirección de la sucursal'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email'
            }),
        }
        labels = {
            'nombre': 'Nombre de la Sucursal',
            'direccion': 'Dirección',
            'telefono': 'Teléfono',
            'email': 'Email',
        }

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Usuario'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )

class PropiedadSearchForm(forms.Form):
    query = forms.CharField(
        label='Buscar',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por dirección, ficha o propietario'
        })
    )

class VentaPropiedadForm(forms.ModelForm):
    class Meta:
        model = VentaPropiedad
        fields = [
            'en_venta',
            'precio_venta',
            'precio_autorizacion',
            'estado',
            'precio_expensas',
            'escribania',
            'observaciones'
        ]
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            'escribania': forms.Textarea(attrs={'rows': 3}),
        }

class MovimientoCajaForm(forms.ModelForm):
    class Meta:
        model = MovimientoCaja
        fields = [
            'tipo',
            'tipo_comprobante',
            'numero_liquidacion',
            'concepto',
            'cuenta',
            'propiedad',
            'fecha_desde',
            'fecha_hasta',
            'monto_efectivo',
            'monto_cheque',
            'monto_tarjeta',
            'monto_deposito',
            'destino_deposito',
            'a_descontar',
            'sucursal',
            'empleado',
            'caja'
        ]

class RegistroForm(forms.ModelForm):
    class Meta:
        model = Registro
        fields = [
            'tipo',
            'tipo_comprobante',
            'fecha_comprobante',
            'liquidacion',
            'cuenta',
            'propiedad',
            'concepto',
            'fecha_desde',
            'fecha_hasta',
            'efectivo',
            'cheques',
            'tarjeta',
            'deposito',
            'qr',
            'tipo_descuento',
            'con_iva',
            'pasa_liquidaciones'
        ]
        widgets = {
            'tipo': forms.RadioSelect,
            'tipo_comprobante': forms.RadioSelect,
            'fecha_comprobante': forms.DateInput(attrs={'type': 'date'}),
            'fecha_desde': forms.DateInput(attrs={'type': 'date'}),
            'fecha_hasta': forms.DateInput(attrs={'type': 'date'}),
            'tipo_descuento': forms.RadioSelect,
        }

class ConceptoForm(forms.ModelForm):
    class Meta:
        model = Concepto
        fields = ['nombre']