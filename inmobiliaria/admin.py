# File: inmobiliaria/admin.py
"""
admin.py:
is a file where you can register your models to make them available in the Django admin interface.
"""


from django.contrib import admin
from .models import Vendedor, Inquilino, Propietario

@admin.register(Vendedor)
class VendedorAdmin(admin.ModelAdmin):
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular', 'comision')
    search_fields = ('dni', 'nombre', 'apellido', 'email')
    list_filter = ('comision',)

@admin.register(Inquilino)
class InquilinoAdmin(admin.ModelAdmin):
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular')
    search_fields = ('dni', 'nombre', 'apellido', 'email')
    list_filter = ('fecha_nacimiento',)

@admin.register(Propietario)
class PropietarioAdmin(admin.ModelAdmin):
    list_display = ('dni', 'nombre', 'apellido', 'email', 'celular', 'cuenta_bancaria')
    search_fields = ('dni', 'nombre', 'apellido', 'email')
    list_filter = ('fecha_nacimiento',)