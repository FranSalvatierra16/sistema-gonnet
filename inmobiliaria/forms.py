from django import forms
from .models import Vendedor, Inquilino, Propietario, Propiedad, PropiedadImagen
from django.contrib.auth.forms import UserCreationForm, UserChangeForm
class VendedorUserCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, help_text='Requerido. 150 caracteres o menos.')
    password1 = forms.CharField(widget=forms.PasswordInput, help_text='Requerido.')
    password2 = forms.CharField(widget=forms.PasswordInput, help_text='Ingrese la misma contraseña para verificar.')

    class Meta:
        model = Vendedor
        fields = ['dni','username', 'nombre', 'apellido', 'email', 'comision','fecha_nacimiento']  # Ajusta los campos según el modelo Vendedor

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return password2

    def save(self, commit=True):
        vendedor = super().save(commit=False)
        if commit:
            vendedor.set_password(self.cleaned_data["password1"])  # Ajusta esto según tu modelo de vendedor
            vendedor.save()
        return vendedor
class VendedorChangeForm(UserChangeForm):
    class Meta:
        model = Vendedor
        fields = ['username', 'dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'comision']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
        }


class InquilinoForm(forms.ModelForm):
    class Meta:
        model = Inquilino
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 'domicilio', 'codigo_postal', 'observaciones', 'garantia']

class PropietarioForm(forms.ModelForm):
    class Meta:
        model = Propietario
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 'domicilio', 'codigo_postal', 'observaciones', 'cuenta_bancaria']


from django import forms
from .models import Propiedad, Propietario

class PropiedadForm(forms.ModelForm):
    propietario = forms.ModelChoiceField(
        queryset=Propietario.objects.all(),
        required=False,
        label="Propietario existente",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    nuevo_propietario = forms.BooleanField(
        required=False,
        label="Crear nuevo propietario",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )

    # Fields for new propietario
    nombre_propietario = forms.CharField(required=False, label="Nombre del propietario")
    apellido_propietario = forms.CharField(required=False, label="Apellido del propietario")
    fecha_nacimiento_propietario = forms.DateField(required=False, label="Fecha de nacimiento")
    email_propietario = forms.EmailField(required=False, label="Email")
    celular_propietario = forms.CharField(required=False, label="Celular")
    tipo_doc_propietario = forms.ChoiceField(required=False, choices=[('DNI', 'DNI'), ('Pasaporte', 'Pasaporte')], label="Tipo de documento")
    dni_propietario = forms.CharField(required=False, label="DNI")
    tipo_ins_propietario = forms.CharField(required=False, label="Tipo de inscripción")
    cuit_propietario = forms.CharField(required=False, label="CUIT")
    localidad_propietario = forms.CharField(required=False, label="Localidad")
    provincia_propietario = forms.CharField(required=False, label="Provincia")
    domicilio_propietario = forms.CharField(required=False, label="Domicilio")
    codigo_postal_propietario = forms.CharField(required=False, label="Código postal")
    observaciones_propietario = forms.CharField(required=False, widget=forms.Textarea, label="Observaciones")
    cuenta_bancaria_propietario = forms.CharField(required=False, label="Cuenta bancaria")
    # Add other fields as necessary for creating a new Propietario

    class Meta:
        model = Propiedad
        fields = [
            'direccion',
            'tipo_inmueble',
            'vista',
            'piso',
            'ambientes',
            'valoracion',
            'cuenta_bancaria',
            'habilitar_precio_diario',
            'precio_diario',
            'habilitar_precio_venta',
            'precio_venta',
            'habilitar_precio_alquiler',
            'precio_alquiler',
            'amoblado',
            'cochera',
            'tv_smart',
            'wifi',
            'dependencia',
            'patio',
            'parrilla',
            'piscina',
            'reciclado',
            'a_estrenar',
            'terraza',
            'balcon',
            'baulera',
            'lavadero',
            'seguridad',
            'vista_al_Mar',
            'vista_panoramica',
            'apto_credito',
            'descripcion',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 5}),
            'valoracion': forms.Select(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Ingrese la dirección'}),
            'precio_diario': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio por día'}),
            'precio_venta': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de venta'}),
            'precio_alquiler': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de alquiler'}),
            'vista': forms.Select(attrs={'class': 'form-control'}),
            'piso': forms.NumberInput(attrs={'placeholder': 'Número de piso'}),
            'ambientes': forms.NumberInput(attrs={'placeholder': 'Número de ambientes'}),
            'cuenta_bancaria': forms.TextInput(attrs={'placeholder': 'Ingrese la cuenta bancaria'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        propietario = cleaned_data.get('propietario')
        nuevo_propietario = cleaned_data.get('nuevo_propietario')
        nombre_propietario = cleaned_data.get('nombre_propietario')
        apellido_propietario = cleaned_data.get('apellido_propietario')

        if not propietario and not nuevo_propietario:
            raise forms.ValidationError("Debe seleccionar un propietario existente o crear uno nuevo.")
        
        if nuevo_propietario and (not nombre_propietario or not apellido_propietario):
            raise forms.ValidationError("Si está creando un nuevo propietario, debe proporcionar nombre y apellido.")

        return cleaned_data

class PropiedadImagenForm(forms.ModelForm):
    class Meta:
        model = PropiedadImagen
        fields = ['imagen']