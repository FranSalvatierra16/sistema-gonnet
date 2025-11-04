#!/usr/bin/env python
"""
Script para migrar datos de JAWSDB a JAWSDB NAVY
"""
import os
import django
import mysql.connector

# Configurar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_gonnet.settings')
django.setup()

# JAWSDB actual (origen)
OLD_DB = {
    'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'oaai2ab9qsc7xvyn',
    'password': 'it2cxhq71iiubhlj',
    'database': 'vgd8ktskappw7cmj',
    'port': 3306,
}

# JAWSDB Navy (destino)
NEW_DB = {
    'host': 'mwgmw3rs78pvwk4e.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'h2jinelj3aiv8emj',
    'password': 'jn8fs396dxf6d1ah',
    'database': 'b4weos59z9jmgxoo',
    'port': 3306,
}

def get_table_names(cursor):
    cursor.execute("SHOW TABLES")
    return [table[0] for table in cursor.fetchall()]

def copy_table_data(old_conn, new_conn, table_name):
    old_cursor = old_conn.cursor()
    new_cursor = new_conn.cursor()
    
    try:
        old_cursor.execute(f"SELECT * FROM `{table_name}`")
        rows = old_cursor.fetchall()
        
        if not rows:
            print(f"   ⏭️  {table_name}: vacía")
            return 0
        
        old_cursor.execute(f"DESCRIBE `{table_name}`")
        columns = [col[0] for col in old_cursor.fetchall()]
        
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join([f'`{col}`' for col in columns])
        insert_query = f"INSERT INTO `{table_name}` ({column_names}) VALUES ({placeholders})"
        
        count = 0
        for row in rows:
            try:
                new_cursor.execute(insert_query, row)
                count += 1
            except Exception as e:
                continue
        
        new_conn.commit()
        print(f"   ✅ {table_name}: {count} filas")
        return count
        
    except Exception as e:
        print(f"   ❌ {table_name}: {e}")
        return 0
    finally:
        old_cursor.close()
        new_cursor.close()

def main():
    print("🚀 Migrando de JAWSDB a JAWSDB NAVY...")
    
    print("📡 Conectando a JAWSDB viejo...")
    old_conn = mysql.connector.connect(**OLD_DB)
    
    print("📡 Conectando a JAWSDB Navy...")
    new_conn = mysql.connector.connect(**NEW_DB)
    
    try:
        old_cursor = old_conn.cursor()
        tables = get_table_names(old_cursor)
        old_cursor.close()
        
        print(f"📊 {len(tables)} tablas\n")
        
        new_cursor = new_conn.cursor()
        new_cursor.execute("SET FOREIGN_KEY_CHECKS=0")
        new_cursor.close()
        
        total_rows = 0
        for i, table in enumerate(tables, 1):
            print(f"[{i}/{len(tables)}] {table}")
            rows = copy_table_data(old_conn, new_conn, table)
            total_rows += rows
        
        new_cursor = new_conn.cursor()
        new_cursor.execute("SET FOREIGN_KEY_CHECKS=1")
        new_cursor.close()
        
        print(f"\n✅ MIGRACIÓN COMPLETADA: {total_rows} filas")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        new_conn.rollback()
    finally:
        old_conn.close()
        new_conn.close()

if __name__ == '__main__':
    main()

