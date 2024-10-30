from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import Vendedor, Inquilino, Propietario, Propiedad, Reserva, Disponibilidad, ImagenPropiedad, Precio,TipoPrecio,TIPOS_INMUEBLES, TIPOS_VISTA, TIPOS_VALORACION
from datetime import datetime
from django.forms import modelformset_factory
# Formulario de creación de Vendedor
class VendedorUserCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, help_text='Requerido. 150 caracteres o menos.')
    password1 = forms.CharField(widget=forms.PasswordInput, help_text='Requerido.')
    password2 = forms.CharField(widget=forms.PasswordInput, help_text='Ingrese la misma contraseña para verificar.')

    class Meta:
        model = Vendedor
        fields = ['dni', 'username', 'nombre', 'apellido', 'email', 'comision', 'fecha_nacimiento', 'nivel']

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return password2

    def save(self, commit=True):
        vendedor = super().save(commit=False)
        vendedor.set_password(self.cleaned_data["password1"])  # Establecer la contraseña
        if commit:
            vendedor.save()
        return vendedor

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

# Formulario de Propietario
class PropietarioForm(forms.ModelForm):
    class Meta:
        model = Propietario
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 'domicilio', 'codigo_postal', 'observaciones', 'cuenta_bancaria']
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


    class Meta:
        model = Propiedad
        fields = [
            'direccion','ubicacion', 'tipo_inmueble', 'vista', 'piso', 'departamento', 'ambientes', 'valoracion', 'cuenta_bancaria',

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
class PrecioForm(forms.ModelForm):
    class Meta:
        model = Precio
        fields = ['tipo_precio', 'precio_por_dia', 'precio_total', 'ajuste_porcentaje']

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
    fecha_inicio = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    fecha_fin = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    tipo_inmueble = forms.ChoiceField(choices=[('', 'Seleccione')] + TIPOS_INMUEBLES, required=False, )
    vista = forms.ChoiceField(choices=[('', 'Seleccione')] + TIPOS_VISTA, required=False)
    ambientes = forms.IntegerField(required=True, min_value=1, label="Ambientes")

    valoracion = forms.ChoiceField(choices=[('', 'Seleccione')] + TIPOS_VALORACION, required=False)
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
        fields = ['propiedad', 'fecha_inicio', 'fecha_fin']
        widgets = {
            'propiedad': forms.HiddenInput(),
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        propiedad = kwargs.pop('propiedad', None)
        super().__init__(*args, **kwargs)
        if propiedad:
            self.fields['propiedad'].initial = propiedad.id
            self.fields['propiedad'].widget = forms.HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')

        if fecha_inicio and fecha_fin and fecha_inicio >= fecha_fin:
            raise forms.ValidationError("La fecha de inicio debe ser anterior a la fecha de fin.")

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