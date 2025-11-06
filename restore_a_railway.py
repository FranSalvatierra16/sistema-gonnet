#!/usr/bin/env python
"""
Script para restaurar backup JSON en Railway (PostgreSQL)
"""
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')

import django
django.setup()

import json
import sys
from datetime import datetime
from decimal import Decimal

if len(sys.argv) < 2:
    print("❌ Error: Debes especificar el archivo de backup")
    print("   Uso: python restore_a_railway.py backup_heroku_XXXXXX.json")
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
    all_data = json.load(f)

print(f"\n📦 Tablas a importar: {len(all_data)}")
print("⚠️  IMPORTANTE: Este proceso puede tardar varios minutos")
print("=" * 60)

# Importar por tabla (en orden)
from django.db import connection

stats = {}

for table_name, rows in all_data.items():
    try:
        if not rows:
            print(f"⏭️  {table_name}: 0 registros (omitido)")
            continue
        
        print(f"\n📋 Procesando {table_name}: {len(rows)} registros...")
        
        # Construir INSERT para PostgreSQL
        if len(rows) > 0:
            columns = list(rows[0].keys())
            placeholders = ', '.join(['%s'] * len(columns))
            columns_str = ', '.join([f'"{col}"' for col in columns])
            
            insert_sql = f'INSERT INTO {table_name} ({columns_str}) VALUES ({placeholders})'
            
            with connection.cursor() as cursor:
                inserted = 0
                for row in rows:
                    try:
                        values = [row[col] for col in columns]
                        cursor.execute(insert_sql, values)
                        inserted += 1
                        
                        if inserted % 100 == 0:
                            print(f"   ✅ {inserted}/{len(rows)} registros insertados...")
                            
                    except Exception as e:
                        print(f"   ⚠️  Error en registro {row.get('id', 'N/A')}: {str(e)[:80]}")
                
                connection.commit()
                stats[table_name] = inserted
                print(f"✅ {table_name}: {inserted} registros importados")
                
    except Exception as e:
        print(f"❌ Error en tabla {table_name}: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "=" * 60)
print("✅ RESTAURACIÓN COMPLETADA")
print("=" * 60)
print(f"\n📊 RESUMEN:")
for table, count in stats.items():
    print(f"   ✅ {table}: {count}")

total = sum(stats.values())
print(f"\n🎯 TOTAL: {total} registros importados")
print("\n✅ ¡Migración completada!")

