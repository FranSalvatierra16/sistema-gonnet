#!/usr/bin/env python
import os
import sys
import django

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import Sucursal, CuentaBancaria

def crear_cuentas_por_defecto():
    """Crear cuentas bancarias por defecto para todas las sucursales"""
    
    sucursales = Sucursal.objects.all()
    print(f"📍 Encontradas {sucursales.count()} sucursales")
    
    for sucursal in sucursales:
        print(f"\n🏢 Procesando sucursal: {sucursal.nombre}")
        
        # Crear Galicia si no existe
        galicia, created = CuentaBancaria.objects.get_or_create(
            sucursal=sucursal,
            nombre='Galicia',
            defaults={
                'tipo': 'banco',
                'orden': 1,
                'activa': True
            }
        )
        if created:
            print(f"  ✅ Creada cuenta: Galicia")
        else:
            print(f"  ℹ️  Ya existe cuenta: Galicia")
        
        # Crear Mercado Pago si no existe
        mp, created = CuentaBancaria.objects.get_or_create(
            sucursal=sucursal,
            nombre='Mercado Pago',
            defaults={
                'tipo': 'billetera',
                'orden': 2,
                'activa': True
            }
        )
        if created:
            print(f"  ✅ Creada cuenta: Mercado Pago")
        else:
            print(f"  ℹ️  Ya existe cuenta: Mercado Pago")
    
    # Mostrar todas las cuentas creadas
    print(f"\n📋 RESUMEN DE CUENTAS BANCARIAS:")
    for sucursal in sucursales:
        cuentas = CuentaBancaria.objects.filter(sucursal=sucursal)
        print(f"\n🏢 {sucursal.nombre}:")
        for cuenta in cuentas:
            estado = "🟢 ACTIVA" if cuenta.activa else "🔴 INACTIVA"
            print(f"  - {cuenta.nombre} ({cuenta.tipo}) {estado}")

if __name__ == '__main__':
    crear_cuentas_por_defecto()
