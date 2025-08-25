#!/usr/bin/env python
import os
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import Propiedad

propiedad_id = 202319

print(f"Buscando propiedad ID: {propiedad_id}")

try:
    propiedad = Propiedad.objects.get(id=propiedad_id)
    print(f"✅ Propiedad encontrada:")
    print(f"   ID: {propiedad.id}")
    print(f"   Dirección: {propiedad.direccion}")
    print(f"   Sucursal: {propiedad.sucursal}")
    print(f"   Precio mensual: {propiedad.info_meses.precio_mensual if hasattr(propiedad, 'info_meses') and propiedad.info_meses else 'No definido'}")
except Propiedad.DoesNotExist:
    print(f"❌ Propiedad {propiedad_id} no existe")
    
    # Buscar propiedades similares
    print(f"\nBuscando propiedades con ID similar...")
    similar = Propiedad.objects.filter(id__in=[202318, 202319, 202320]).values('id', 'direccion', 'sucursal')
    for prop in similar:
        print(f"   ID: {prop['id']}, Dirección: {prop['direccion']}, Sucursal: {prop['sucursal']}") 