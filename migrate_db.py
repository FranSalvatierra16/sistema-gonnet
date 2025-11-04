#!/usr/bin/env python
"""
Script para migrar datos de la base de datos vieja a JawsDB
"""
import os
import django
import mysql.connector
from mysql.connector import Error

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

# Credenciales base de datos VIEJA
OLD_DB = {
    'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'oaai2ab9qsc7xvyn',
    'password': 'it2cxhq71iiubhlj',
    'database': 'vgd8ktskappw7cmj',
    'port': 3306,
}

# Credenciales base de datos NUEVA (JawsDB)
NEW_DB = {
    'host': 's0znzigqvfehvff5.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'm4l9g6i6lqzt2h25',
    'password': 'smlq7dj0f9bxoerr',
    'database': 'gm8f887gtmlwtvg6',
    'port': 3306,
}

def get_table_names(cursor):
    """Obtener lista de tablas"""
    cursor.execute("SHOW TABLES")
    return [table[0] for table in cursor.fetchall()]

def copy_table_data(old_conn, new_conn, table_name):
    """Copiar datos de una tabla"""
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()
    
    try:
        # Obtener datos de la tabla vieja
        old_cursor.execute(f"SELECT * FROM `{table_name}`")
        rows = old_cursor.fetchall()
        
        if not rows:
            print(f"   ⏭️  {table_name}: vacía, saltando")
            return 0
        
        # Obtener nombres de columnas
        old_cursor.execute(f"DESCRIBE `{table_name}`")
        columns = [col[0] for col in old_cursor.fetchall()]
        
        # Preparar INSERT
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join([f'`{col}`' for col in columns])
        insert_query = f"INSERT INTO `{table_name}` ({column_names}) VALUES ({placeholders})"
        
        # Insertar datos en la nueva BD
        count = 0
        for row in rows:
            try:
                new_cursor.execute(insert_query, row)
                count += 1
            except Exception as e:
                print(f"      ⚠️  Error en fila de {table_name}: {e}")
                continue
        
        new_conn.commit()
        print(f"   ✅ {table_name}: {count} filas copiadas")
        return count
        
    except Exception as e:
        print(f"   ❌ Error copiando {table_name}: {e}")
        return 0
    finally:
        old_cursor.close()
        new_cursor.close()

def main():
    print("🚀 Iniciando migración de base de datos...")
    print(f"   Origen: {OLD_DB['host']} ({OLD_DB['database']})")
    print(f"   Destino: {NEW_DB['host']} ({NEW_DB['database']})")
    print()
    
    # Conectar a ambas bases de datos
    print("📡 Conectando a base de datos vieja...")
    old_conn = mysql.connector.connect(**OLD_DB)
    
    print("📡 Conectando a JawsDB...")
    new_conn = mysql.connector.connect(**NEW_DB)
    
    try:
        # Obtener lista de tablas
        old_cursor = old_conn.cursor()
        tables = get_table_names(old_cursor)
        old_cursor.close()
        
        print(f"📊 Encontradas {len(tables)} tablas")
        print()
        
        # Deshabilitar foreign key checks temporalmente
        new_cursor = new_conn.cursor()
        new_cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        new_cursor.close()
        
        # Copiar cada tabla
        total_rows = 0
        for i, table in enumerate(tables, 1):
            print(f"[{i}/{len(tables)}] Copiando tabla: {table}")
            rows = copy_table_data(old_conn, new_conn, table)
            total_rows += rows
        
        # Rehabilitar foreign key checks
        new_cursor = new_conn.cursor()
        new_cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        new_cursor.close()
        
        print()
        print(f"✅ MIGRACIÓN COMPLETADA")
        print(f"   Total de filas copiadas: {total_rows}")
        
    except Exception as e:
        print(f"❌ ERROR durante migración: {e}")
        new_conn.rollback()
    finally:
        old_conn.close()
        new_conn.close()
        print()
        print("🔌 Conexiones cerradas")

if __name__ == '__main__':
    main()

