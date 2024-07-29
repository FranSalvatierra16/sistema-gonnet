# File: inmobiliaria/forms.py

from django import forms
from .models import Vendedor, Inquilino, Propietario

class VendedorForm(forms.ModelForm):
    class Meta:
        model = Vendedor
        fields = ['dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'comision', 'observaciones']

class InquilinoForm(forms.ModelForm):
    class Meta:
        model = Inquilino
        fields = ['dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'garantia', 'observaciones']

class PropietarioForm(forms.ModelForm):
    class Meta:
        model = Propietario
        fields = ['dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 'cuenta_bancaria', 'observaciones']