#!/usr/bin/env python
"""
Script para hacer backup de la base de datos de Heroku a JSON
"""
import os
import django
import json
from datetime import datetime

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from django.core import serializers
from django.apps import apps

print("🔍 Iniciando backup de Heroku...")
print("=" * 60)

# Obtener todos los modelos de la app inmobiliaria
inmobiliaria_models = apps.get_app_config('inmobiliaria').get_models()

# Ordenar modelos para evitar problemas de dependencias
model_order = [
    'Sucursal',
    'Vendedor',
    'Concepto',
    'CuentaBancaria',
    'Propietario',
    'Inquilino',
    'Propiedad',
    'Disponibilidad',
    'HistorialDisponibilidad',
    'Precio',
    'Reserva',
    'ContratoAlquiler',
    'CuotaMensual',
    'Caja',
    'MovimientoCaja',
    'Recibo',
    'ComisionVendedor',
    'ValeVendedor',
]

all_data = []
stats = {}

for model_name in model_order:
    try:
        model = apps.get_model('inmobiliaria', model_name)
        objects = model.objects.all()
        count = objects.count()
        
        if count > 0:
            print(f"📦 Exportando {model_name}: {count} registros...")
            data = serializers.serialize('python', objects)
            all_data.extend(data)
            stats[model_name] = count
        else:
            print(f"⏭️  {model_name}: 0 registros (omitido)")
            
    except Exception as e:
        print(f"⚠️  Error con {model_name}: {e}")

# Guardar en archivo JSON
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
filename = f'backup_heroku_{timestamp}.json'

print("\n" + "=" * 60)
print(f"💾 Guardando backup en: {filename}")

with open(filename, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2, default=str)

print("=" * 60)
print("✅ BACKUP COMPLETADO")
print("=" * 60)
print("\n📊 RESUMEN:")
for model_name, count in stats.items():
    print(f"   {model_name}: {count}")

total = sum(stats.values())
print(f"\n🎯 TOTAL: {total} registros exportados")
print(f"📁 Archivo: {filename}")
print("\n🚀 SIGUIENTE PASO:")
print(f"   Sube este archivo a Railway y ejecuta:")
print(f"   python restore_railway.py {filename}")

