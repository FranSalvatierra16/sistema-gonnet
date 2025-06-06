import MySQLdb

# Conexión a la base de datos
db = MySQLdb.connect(
    host='tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com',
    user='oaai2ab9qsc7xvyn',
    passwd='it2cxhq71iiubhlj',
    db='vgd8ktskappw7cmj'
)

cursor = db.cursor()

try:
    # Mostrar los índices de la tabla
    cursor.execute("SHOW INDEX FROM inmobiliaria_propiedad;")
    indices = cursor.fetchall()
    print("Índices encontrados:")
    for indice in indices:
        print(indice)
except Exception as e:
    print(f"Error al obtener los índices: {e}")
finally:
    cursor.close()
    db.close() 