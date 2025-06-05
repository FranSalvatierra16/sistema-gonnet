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
    # Intentar eliminar el índice
    cursor.execute("ALTER TABLE inmobiliaria_propiedad DROP INDEX inmobiliaria_propiedad_llave_key;")
    db.commit()
    print("Índice eliminado con éxito")
except Exception as e:
    print(f"Error al eliminar el índice: {e}")
finally:
    cursor.close()
    db.close() 