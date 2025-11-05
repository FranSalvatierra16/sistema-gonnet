#!/usr/bin/env python
"""
Script para migrar datos de JAWSDB a JAWSDB_KITEFIN
"""
import mysql.connector
import os

# Configuración de bases de datos
SOURCE_DB = {
    'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'oaai2ab9qsc7xvyn',
    'password': 'it2cxhq71iiubhlj',
    'database': 'vgd8ktskappw7cmj',
    'port': 3306
}

TARGET_DB = {
    'host': 'k3xio06abqa902qt.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'zkl7lzpzr7tia4z6',
    'password': 'rpb0hf53kiqtq9rb',
    'database': 'gpw9u5s4w4zlpsr4',
    'port': 3306
}

print("🔄 Iniciando migración de datos...")
print(f"📤 Origen: {SOURCE_DB['host']}/{SOURCE_DB['database']}")
print(f"📥 Destino: {TARGET_DB['host']}/{TARGET_DB['database']}")

try:
    # Conectar a ambas bases de datos
    print("\n📡 Conectando a base de datos origen...")
    source_conn = mysql.connector.connect(**SOURCE_DB)
    source_cursor = source_conn.cursor()
    
    print("📡 Conectando a base de datos destino...")
    target_conn = mysql.connector.connect(**TARGET_DB)
    target_cursor = target_conn.cursor()
    
    # Obtener todas las tablas
    source_cursor.execute("SHOW TABLES")
    tables = [table[0] for table in source_cursor.fetchall()]
    
    print(f"\n📊 Encontradas {len(tables)} tablas para migrar")
    
    # Deshabilitar foreign key checks en destino
    target_cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    
    for table in tables:
        print(f"\n🔄 Migrando tabla: {table}")
        
        # Vaciar tabla destino
        target_cursor.execute(f"TRUNCATE TABLE `{table}`")
        
        # Copiar datos
        source_cursor.execute(f"SELECT * FROM `{table}`")
        rows = source_cursor.fetchall()
        
        if rows:
            # Obtener nombres de columnas
            source_cursor.execute(f"DESCRIBE `{table}`")
            columns = [col[0] for col in source_cursor.fetchall()]
            
            placeholders = ', '.join(['%s'] * len(columns))
            insert_query = f"INSERT INTO `{table}` ({', '.join(f'`{col}`' for col in columns)}) VALUES ({placeholders})"
            
            # Insertar en lotes de 1000
            batch_size = 1000
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                target_cursor.executemany(insert_query, batch)
                target_conn.commit()
                print(f"   ✅ Insertadas {len(batch)} filas ({i + len(batch)}/{len(rows)})")
        else:
            print(f"   ⏭️  Tabla vacía")
    
    # Rehabilitar foreign key checks
    target_cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    target_conn.commit()
    
    print("\n🎉 ✅ MIGRACIÓN COMPLETADA CON ÉXITO")
    
    source_conn.close()
    target_conn.close()
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

