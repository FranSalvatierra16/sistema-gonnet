#!/usr/bin/env python
"""
Script para restaurar el historial de disponibilidad desde un backup JSON
"""
import os
import django
import json
import sys
from datetime import datetime

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

from inmobiliaria.models import Propiedad, HistorialDisponibilidad

if len(sys.argv) < 3:
    print("❌ Error: Debes especificar el archivo de backup y el ID de la propiedad")
    print("   Uso: python restaurar_historial_desde_backup.py backup_heroku_XXXXXX.json PROPERTY_ID")
    print("\n   Ejemplo: python restaurar_historial_desde_backup.py backup_heroku_20251111_213534.json 123")
    sys.exit(1)

filename = sys.argv[1]
propiedad_id = int(sys.argv[2])

if not os.path.exists(filename):
    print(f"❌ Error: El archivo '{filename}' no existe")
    sys.exit(1)

print("🔍 Iniciando restauración de historial desde backup...")
print("=" * 60)
print(f"📁 Archivo: {filename}")
print(f"🏠 Propiedad ID: {propiedad_id}")
print("=" * 60)

# Verificar que la propiedad existe
try:
    propiedad = Propiedad.objects.get(id=propiedad_id)
    print(f"✅ Propiedad encontrada: {propiedad.direccion}")
except Propiedad.DoesNotExist:
    print(f"❌ Error: La propiedad {propiedad_id} no existe")
    sys.exit(1)

# Leer archivo JSON
with open(filename, 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"\n📦 Registros en backup: {len(data)}")

# Buscar registros de HistorialDisponibilidad para esta propiedad
historiales_backup = []
for obj_data in data:
    if obj_data.get('model') == 'inmobiliaria.historialdisponibilidad':
        # Verificar si pertenece a esta propiedad
        fields = obj_data.get('fields', {})
        if fields.get('propiedad') == propiedad_id:
            historiales_backup.append(obj_data)

print(f"📋 Historiales encontrados en backup: {len(historiales_backup)}")

if not historiales_backup:
    print("⚠️  No se encontraron historiales para esta propiedad en el backup")
    print("   El historial se reconstruirá automáticamente desde las reservas y disponibilidades actuales")
    sys.exit(0)

# Mostrar resumen
print("\n📊 Resumen del historial en backup:")
for h in historiales_backup[:5]:  # Mostrar solo los primeros 5
    fields = h.get('fields', {})
    print(f"   - {fields.get('fecha_inicio')} al {fields.get('fecha_fin')} - {fields.get('estado')}")
if len(historiales_backup) > 5:
    print(f"   ... y {len(historiales_backup) - 5} más")

# Confirmar
print("\n⚠️  ADVERTENCIA: Esto eliminará el historial actual y lo reemplazará con el del backup")
respuesta = input("¿Deseas continuar? (s/n): ")

if respuesta.lower() != 's':
    print("❌ Operación cancelada")
    sys.exit(0)

# Eliminar historial actual
count_actual = HistorialDisponibilidad.objects.filter(propiedad=propiedad).count()
HistorialDisponibilidad.objects.filter(propiedad=propiedad).delete()
print(f"🧹 Eliminados {count_actual} registros de historial actual")

# Restaurar desde backup
from django.core import serializers
from django.db import transaction

restaurados = 0
errores = 0

with transaction.atomic():
    for obj_data in historiales_backup:
        try:
            # Deserializar y guardar
            for obj in serializers.deserialize('python', [obj_data]):
                obj.save()
                restaurados += 1
        except Exception as e:
            print(f"⚠️  Error al restaurar registro: {e}")
            errores += 1

print("\n" + "=" * 60)
print(f"✅ Restauración completada:")
print(f"   - Restaurados: {restaurados}")
print(f"   - Errores: {errores}")
print("=" * 60)

