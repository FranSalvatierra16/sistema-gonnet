# Generated manually to add caja_id column to MovimientoCaja

from django.db import migrations


def add_caja_id_column(apps, schema_editor):
    """Agregar columna caja_id compatible MySQL/PostgreSQL"""
    with schema_editor.connection.cursor() as cursor:
        # Verificar si la columna ya existe
        if schema_editor.connection.vendor == 'mysql':
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND COLUMN_NAME = 'caja_id'
            """)
        elif schema_editor.connection.vendor == 'postgresql':
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = 'inmobiliaria_movimientocaja'
                AND column_name = 'caja_id'
            """)
        
        column_exists = cursor.fetchone()[0] > 0
        
        # Agregar columna si no existe
        if not column_exists:
            cursor.execute("""
                ALTER TABLE inmobiliaria_movimientocaja 
                ADD COLUMN caja_id bigint NULL
            """)
        
        # Crear cajas iniciales para cada sucursal
        if schema_editor.connection.vendor == 'mysql':
            cursor.execute("""
                INSERT IGNORE INTO inmobiliaria_caja 
                (numero, sucursal_id, fecha_apertura, saldo_inicial, estado, usuario_apertura_id, observaciones_apertura)
                SELECT 
                    1, s.id, NOW(), 0.00, 'abierta', 1, 'Caja inicial automática'
                FROM inmobiliaria_sucursal s
                WHERE NOT EXISTS (
                    SELECT 1 FROM inmobiliaria_caja c WHERE c.sucursal_id = s.id
                )
            """)
        elif schema_editor.connection.vendor == 'postgresql':
            cursor.execute("""
                INSERT INTO inmobiliaria_caja 
                (numero, sucursal_id, fecha_apertura, saldo_inicial, estado, usuario_apertura_id, observaciones_apertura)
                SELECT 
                    1, s.id, NOW(), 0.00, 'abierta', 1, 'Caja inicial automática'
                FROM inmobiliaria_sucursal s
                WHERE NOT EXISTS (
                    SELECT 1 FROM inmobiliaria_caja c WHERE c.sucursal_id = s.id
                )
                ON CONFLICT DO NOTHING
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0026_recreate_caja_table_complete'),
    ]

    operations = [
        migrations.RunPython(add_caja_id_column, reverse_code=migrations.RunPython.noop),
    ] 