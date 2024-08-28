from django import forms
from .models import Vendedor, Inquilino, Propietario, Propiedad
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



class PropiedadForm(forms.ModelForm):

    class Meta:
        model = Propiedad
        fields = [
            'direccion',
            'descripcion',
            'vista',
            'piso',
            'ambientes',
            'cuenta_bancaria',
            'habilitar_precio_diario',
            'precio_diario',
            'habilitar_precio_venta',
            'precio_venta',
            'habilitar_precio_alquiler',
            'precio_alquiler',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ingrese una descripción'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Ingrese la dirección'}),
            'precio_diario': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio por día'}),
            'precio_venta': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de venta'}),
            'precio_alquiler': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de alquiler'}),
            'vista': forms.CheckboxInput(),
            'piso': forms.NumberInput(attrs={'placeholder': 'Número de piso'}),
            'ambientes': forms.NumberInput(attrs={'placeholder': 'Número de ambientes'}),
            'cuenta_bancaria': forms.TextInput(attrs={'placeholder': 'Ingrese la cuenta bancaria'}),
        }


