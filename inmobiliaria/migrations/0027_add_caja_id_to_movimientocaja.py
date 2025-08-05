# Generated manually to add caja_id column to MovimientoCaja

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0026_recreate_caja_table_complete'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            SET @column_exists = (
                SELECT COUNT(*)
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME = 'inmobiliaria_movimientocaja'
                AND COLUMN_NAME = 'caja_id'
            );
            SET @sql = IF(@column_exists = 0, 
                'ALTER TABLE inmobiliaria_movimientocaja ADD COLUMN caja_id bigint NULL', 
                'SELECT "Column caja_id already exists"'
            );
            PREPARE stmt FROM @sql;
            EXECUTE stmt;
            DEALLOCATE PREPARE stmt;
            
            -- Crear una caja inicial para cada sucursal si no existe
            INSERT IGNORE INTO inmobiliaria_caja 
            (numero, sucursal_id, fecha_apertura, saldo_inicial, estado, usuario_apertura_id, observaciones_apertura)
            SELECT 
                1 as numero,
                s.id as sucursal_id,
                NOW() as fecha_apertura,
                0.00 as saldo_inicial,
                'abierta' as estado,
                1 as usuario_apertura_id,
                'Caja inicial automática' as observaciones_apertura
            FROM inmobiliaria_sucursal s
            WHERE NOT EXISTS (
                SELECT 1 FROM inmobiliaria_caja c WHERE c.sucursal_id = s.id
            );
            """,
            reverse_sql="ALTER TABLE inmobiliaria_movimientocaja DROP COLUMN IF EXISTS caja_id;"
        ),
    ] 