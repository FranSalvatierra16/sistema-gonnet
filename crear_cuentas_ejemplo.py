#!/usr/bin/env python
"""
Script para crear cuentas bancarias de ejemplo para cada sucursal
Ejecutar con: python manage.py shell < crear_cuentas_ejemplo.py
"""

from inmobiliaria.models.sucursal import Sucursal, CuentaBancaria

def crear_cuentas_ejemplo():
    """Crear cuentas bancarias de ejemplo para todas las sucursales"""
    
    # Obtener todas las sucursales
    sucursales = Sucursal.objects.all()
    
    if not sucursales.exists():
        print("❌ No hay sucursales en la base de datos")
        return
    
    cuentas_ejemplo = [
        {
            'nombre_banco': 'Banco Provincia',
            'alias': 'GONNET-ALQUILERES',
            'numero_cuenta': '1234567890123456789012',
            'tipo_cuenta': 'banco',
            'activa': True
        },
        {
            'nombre_banco': 'Banco Galicia',
            'alias': 'GONNET-DEPOSITOS',
            'numero_cuenta': '9876543210987654321098',
            'tipo_cuenta': 'banco',
            'activa': True
        },
        {
            'nombre_banco': 'Mercado Pago',
            'alias': 'GONNET-MP',
            'numero_cuenta': '0000003100001234567890',
            'tipo_cuenta': 'billetera',
            'activa': True
        },
        {
            'nombre_banco': 'Ualá',
            'alias': 'GONNET-UALA',
            'numero_cuenta': '0000003200001234567890',
            'tipo_cuenta': 'billetera',
            'activa': False  # Inactiva por defecto
        }
    ]
    
    cuentas_creadas = 0
    
    for sucursal in sucursales:
        print(f"🏢 Procesando sucursal: {sucursal.nombre}")
        
        for cuenta_data in cuentas_ejemplo:
            # Verificar si ya existe una cuenta similar
            cuenta_existente = CuentaBancaria.objects.filter(
                sucursal=sucursal,
                nombre_banco=cuenta_data['nombre_banco'],
                alias=cuenta_data['alias']
            ).first()
            
            if not cuenta_existente:
                cuenta = CuentaBancaria.objects.create(
                    sucursal=sucursal,
                    **cuenta_data
                )
                print(f"  ✅ Creada: {cuenta.nombre_banco} - {cuenta.alias}")
                cuentas_creadas += 1
            else:
                print(f"  ⚠️ Ya existe: {cuenta_data['nombre_banco']} - {cuenta_data['alias']}")
    
    print(f"\n🎉 Proceso completado!")
    print(f"📊 Cuentas creadas: {cuentas_creadas}")
    print(f"🏢 Sucursales procesadas: {sucursales.count()}")

if __name__ == "__main__":
    crear_cuentas_ejemplo()
