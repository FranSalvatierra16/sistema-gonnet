from django import forms
from .models import Vendedor, Inquilino, Propietario, Propiedad

class VendedorForm(forms.ModelForm):
    class Meta:
        model = Vendedor
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 'domicilio', 'codigo_postal', 'observaciones', 'comision']

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
            'precio_tipo',
            'precio',
            'descripcion',
            'vista',
            'piso',
            'ambientes',
            'cuenta_bancaria',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Ingrese la dirección'}),
            'precio': forms.NumberInput(attrs={'step': 0.01}),
            'vista': forms.CheckboxInput(),
            'piso': forms.NumberInput(),
            'ambientes': forms.NumberInput(),
        }


