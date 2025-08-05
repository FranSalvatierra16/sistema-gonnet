# Generated manually to fix Caja table columns

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0024_create_basic_caja_table'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            -- Agregar columnas faltantes si no existen
            ALTER TABLE inmobiliaria_caja 
            ADD COLUMN IF NOT EXISTS usuario_apertura_id bigint NULL,
            ADD COLUMN IF NOT EXISTS usuario_cierre_id bigint NULL,
            ADD COLUMN IF NOT EXISTS observaciones_apertura longtext NOT NULL DEFAULT '',
            ADD COLUMN IF NOT EXISTS observaciones_cierre longtext NOT NULL DEFAULT '';
            
            -- Actualizar usuario_apertura_id con empleado_id si existe
            UPDATE inmobiliaria_caja SET usuario_apertura_id = empleado_id WHERE usuario_apertura_id IS NULL AND empleado_id IS NOT NULL;
            
            -- Eliminar empleado_id si existe
            ALTER TABLE inmobiliaria_caja DROP COLUMN IF EXISTS empleado_id;
            """,
            reverse_sql=""
        ),
    ] 