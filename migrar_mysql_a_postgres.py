#!/usr/bin/env python3
"""
Migración directa de MySQL (Heroku) a PostgreSQL (Railway)
"""
import mysql.connector
import psycopg2
from datetime import datetime
import json

print("🔄 MIGRACIÓN MYSQL → POSTGRESQL")
print("=" * 60)

# Configuración MySQL (Heroku)
mysql_config = {
    'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'oaai2ab9qsc7xvyn',
    'password': 'it2cxhq71iiubhlj',
    'database': 'vgd8ktskappw7cmj',
    'port': 3306,
    'use_pure': True
}

# Configuración PostgreSQL (Railway)
# NOTA: Cambia esto por el DATABASE_URL público de Railway si existe
# O ejecuta este script EN Railway con: railway run python migrar_mysql_a_postgres.py
postgres_url = "postgresql://postgres:IJRJTlvqpkpWQHdoSEosGnzYDlnntilh@postgres.railway.internal:5432/railway"

print("\n📥 Conectando a MySQL (Heroku)...")
try:
    mysql_conn = mysql.connector.connect(**mysql_config)
    print("✅ MySQL conectado")
except Exception as e:
    print(f"❌ Error MySQL: {e}")
    exit(1)

print("\n📤 Conectando a PostgreSQL (Railway)...")
try:
    postgres_conn = psycopg2.connect(postgres_url)
    print("✅ PostgreSQL conectado")
except Exception as e:
    print(f"❌ Error PostgreSQL: {e}")
    print("\n⚠️  EJECUTA ESTE SCRIPT EN RAILWAY:")
    print("   railway run python migrar_mysql_a_postgres.py")
    exit(1)

# Tablas a migrar
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

mysql_cursor = mysql_conn.cursor(dictionary=True)
postgres_cursor = postgres_conn.cursor()

total_migrated = 0

for table in tables:
    try:
        # Leer de MySQL
        mysql_cursor.execute(f"SELECT * FROM {table}")
        rows = mysql_cursor.fetchall()
        
        if not rows:
            print(f"⏭️  {table}: 0 registros")
            continue
        
        print(f"\n📋 Migrando {table}: {len(rows)} registros...")
        
        # Preparar INSERT para PostgreSQL
        columns = list(rows[0].keys())
        placeholders = ', '.join(['%s'] * len(columns))
        columns_str = ', '.join([f'"{col}"' for col in columns])
        
        insert_sql = f'INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT DO NOTHING'
        
        migrated = 0
        for row in rows:
            try:
                values = [row[col] for col in columns]
                postgres_cursor.execute(insert_sql, values)
                migrated += 1
                
                if migrated % 100 == 0:
                    print(f"   ✅ {migrated}/{len(rows)}...")
                    postgres_conn.commit()
                    
            except Exception as e:
                print(f"   ⚠️  Error en registro {row.get('id', 'N/A')}: {str(e)[:80]}")
        
        postgres_conn.commit()
        total_migrated += migrated
        print(f"✅ {table}: {migrated} registros migrados")
        
    except Exception as e:
        print(f"❌ Error en tabla {table}: {e}")

mysql_cursor.close()
mysql_conn.close()
postgres_cursor.close()
postgres_conn.close()

print("\n" + "=" * 60)
print("✅ MIGRACIÓN COMPLETADA")
print("=" * 60)
print(f"🎯 Total migrado: {total_migrated} registros")

