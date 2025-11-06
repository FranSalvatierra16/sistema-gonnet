#!/usr/bin/env python
"""
Script para restaurar backup JSON en Railway (PostgreSQL)
"""
import os
import django
import json
import sys

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from django.core import serializers

if len(sys.argv) < 2:
    print("❌ Error: Debes especificar el archivo de backup")
    print("   Uso: python restore_railway.py backup_heroku_XXXXXX.json")
    sys.exit(1)

filename = sys.argv[1]

if not os.path.exists(filename):
    print(f"❌ Error: El archivo '{filename}' no existe")
    sys.exit(1)

print("🔍 Iniciando restauración en Railway (PostgreSQL)...")
print("=" * 60)
print(f"📁 Archivo: {filename}")
print("=" * 60)

# Leer archivo JSON
with open(filename, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"\n📦 Registros a importar: {len(data)}")
print("\n⚠️  IMPORTANTE: Este proceso puede tardar varios minutos")
print("=" * 60)

# Deserializar y guardar
try:
    objects_created = 0
    errors = 0
    
    for obj_data in data:
        try:
            # Deserializar objeto
            for obj in serializers.deserialize('python', [obj_data]):
                obj.save()
                objects_created += 1
                
                if objects_created % 100 == 0:
                    print(f"✅ Procesados: {objects_created}/{len(data)}")
                    
        except Exception as e:
            errors += 1
            model = obj_data.get('model', 'unknown')
            pk = obj_data.get('pk', 'unknown')
            print(f"⚠️  Error en {model} (pk={pk}): {str(e)[:100]}")
    
    print("\n" + "=" * 60)
    print("✅ RESTAURACIÓN COMPLETADA")
    print("=" * 60)
    print(f"\n📊 RESUMEN:")
    print(f"   ✅ Creados: {objects_created}")
    print(f"   ⚠️  Errores: {errors}")
    print(f"   📦 Total procesado: {len(data)}")
    
    if errors > 0:
        print(f"\n⚠️  Hubo {errors} errores durante la importación")
        print("   Esto puede ser normal debido a constraints de FK")
    
    print("\n🎯 ¡Migración completada!")
    
except Exception as e:
    print(f"\n❌ ERROR CRÍTICO: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

