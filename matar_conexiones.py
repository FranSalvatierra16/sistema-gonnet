#!/usr/bin/env python
"""
Script de emergencia para matar conexiones zombies en MySQL
"""
import os
import MySQLdb

# Credenciales de la base de datos (usa las mismas de settings.py)
DB_CONFIG = {
    'host': 'tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    'user': 'oaai2ab9qsc7xvyn',
    'password': 'it2cxhq71iiubhlj',
    'database': 'vgd8ktskappw7cmj',
    'port': 3306
}

try:
    print("🔌 Conectando a MySQL...")
    conn = MySQLdb.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Ver todas las conexiones del usuario
    print("\n📊 Conexiones activas:")
    cursor.execute("SHOW PROCESSLIST")
    procesos = cursor.fetchall()
    
    total_conexiones = 0
    conexiones_a_matar = []
    
    for proceso in procesos:
        process_id, user, host, db, command, time, state, info = proceso
        if user == DB_CONFIG['user']:
            total_conexiones += 1
            print(f"  ID: {process_id}, Command: {command}, Time: {time}s, State: {state}")
            
            # Marcar para eliminar si:
            # - No es la conexión actual
            # - Time > 60 segundos (conexión vieja)
            # - Command es 'Sleep' (inactiva)
            if command == 'Sleep' and time > 60:
                conexiones_a_matar.append(process_id)
    
    print(f"\n📈 Total conexiones: {total_conexiones}")
    print(f"🗑️ Conexiones a cerrar: {len(conexiones_a_matar)}")
    
    # Matar conexiones zombies
    if conexiones_a_matar:
        print("\n🔫 Cerrando conexiones zombies...")
        for process_id in conexiones_a_matar:
            try:
                cursor.execute(f"KILL {process_id}")
                print(f"  ✅ Conexión {process_id} cerrada")
            except Exception as e:
                print(f"  ❌ Error cerrando {process_id}: {e}")
        
        conn.commit()
        print(f"\n✅ {len(conexiones_a_matar)} conexiones cerradas exitosamente")
    else:
        print("\n✅ No hay conexiones zombies para cerrar")
    
    # Verificar conexiones restantes
    cursor.execute("SHOW PROCESSLIST")
    procesos_final = cursor.fetchall()
    conexiones_final = sum(1 for p in procesos_final if p[1] == DB_CONFIG['user'])
    
    print(f"\n📊 Conexiones restantes: {conexiones_final}/15")
    
    cursor.close()
    conn.close()
    print("\n✅ Script completado")
    
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nSi el error es 'max_user_connections', necesitás:")
    print("1. Contactar al administrador de AWS RDS")
    print("2. Aumentar el límite de max_user_connections")
    print("3. O usar un usuario diferente temporalmente")

