#!/usr/bin/env python
"""
Backup directo de MySQL usando mysql-connector-python
"""
import mysql.connector
import json
from datetime import datetime, date
from decimal import Decimal

print("🔍 Conectando a MySQL de Heroku...")
print("=" * 60)

# Conectar a MySQL
try:
    conn = mysql.connector.connect(
        host='tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
        user='oaai2ab9qsc7xvyn',
        password='it2cxhq71iiubhlj',
        database='vgd8ktskappw7cmj',
        port=3306,
        use_pure=True  # ✅ Evitar problemas de SSL
    )
    
    cursor = conn.cursor(dictionary=True)
    print("✅ Conectado exitosamente")
    
except Exception as e:
    print(f"❌ Error de conexión: {e}")
    exit(1)

# Función para convertir valores no serializables
def convert_value(val):
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='ignore')
    return val

# Tablas a exportar (en orden de dependencias)
tables = [
    'inmobiliaria_sucursal',
    'inmobiliaria_vendedor',
    'inmobiliaria_concepto',
    'inmobiliaria_cuentabancaria',
    'inmobiliaria_propietario',
    'inmobiliaria_inquilino',
    'inmobiliaria_propiedad',
    'inmobiliaria_disponibilidad',
    'inmobiliaria_historialdisponibilidad',
    'inmobiliaria_precio',
    'inmobiliaria_reserva',
    'inmobiliaria_contratoalquiler',
    'inmobiliaria_cuotamensual',
    'inmobiliaria_caja',
    'inmobiliaria_movimientocaja',
    'inmobiliaria_recibo',
    'inmobiliaria_comisionvendedor',
    'inmobiliaria_valevendedor',
]

all_data = {}
total_rows = 0

for table in tables:
    try:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        
        if rows:
            # Convertir valores no serializables
            converted_rows = []
            for row in rows:
                converted_row = {k: convert_value(v) for k, v in row.items()}
                converted_rows.append(converted_row)
            
            all_data[table] = converted_rows
            count = len(rows)
            total_rows += count
            print(f"📦 {table}: {count} registros")
        else:
            print(f"⏭️  {table}: 0 registros")
            
    except Exception as e:
        print(f"⚠️  Error con {table}: {e}")

# Guardar JSON
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
filename = f'backup_heroku_{timestamp}.json'

with open(filename, 'w', encoding='utf-8') as f:
    json.dump(all_data, f, ensure_ascii=False, indent=2, default=str)

cursor.close()
conn.close()

import os
size = os.path.getsize(filename)

print("\n" + "=" * 60)
print("✅ BACKUP COMPLETADO")
print("=" * 60)
print(f"📁 Archivo: {filename}")
print(f"💾 Tamaño: {size / 1024 / 1024:.2f} MB")
print(f"📊 Total registros: {total_rows}")
print("\n🚀 SIGUIENTE PASO:")
print("   Sube este archivo a Railway y usa un script de import")

