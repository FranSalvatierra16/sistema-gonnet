# Generated manually to add fichado_por field

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def add_fichado_por_fields(apps, schema_editor):
    """Agregar campos fichado_por y fecha_fichado solo si no existen"""
    db_alias = schema_editor.connection.alias
    
    # Verificar si los campos ya existen
    with schema_editor.connection.cursor() as cursor:
        # Verificar fichado_por_id
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'inmobiliaria_propiedad' 
            AND COLUMN_NAME = 'fichado_por_id'
        """)
        fichado_por_exists = cursor.fetchone()[0] > 0
        
        # Verificar fecha_fichado
        cursor.execute("""
            SELECT COUNT(*) 
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = DATABASE() 
            AND TABLE_NAME = 'inmobiliaria_propiedad' 
            AND COLUMN_NAME = 'fecha_fichado'
        """)
        fecha_fichado_exists = cursor.fetchone()[0] > 0
        
        # Agregar fichado_por_id si no existe
        if not fichado_por_exists:
            cursor.execute("""
                ALTER TABLE inmobiliaria_propiedad 
                ADD COLUMN fichado_por_id bigint NULL
            """)
            cursor.execute("""
                ALTER TABLE inmobiliaria_propiedad 
                ADD CONSTRAINT inmobiliaria_propiedad_fichado_por_id_fk 
                FOREIGN KEY (fichado_por_id) REFERENCES auth_user(id) ON DELETE SET NULL
            """)
        
        # Agregar fecha_fichado si no existe
        if not fecha_fichado_exists:
            cursor.execute("""
                ALTER TABLE inmobiliaria_propiedad 
                ADD COLUMN fecha_fichado datetime(6) NULL
            """)


def remove_fichado_por_fields(apps, schema_editor):
    """Remover campos fichado_por y fecha_fichado"""
    with schema_editor.connection.cursor() as cursor:
        try:
            cursor.execute("ALTER TABLE inmobiliaria_propiedad DROP FOREIGN KEY inmobiliaria_propiedad_fichado_por_id_fk")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE inmobiliaria_propiedad DROP COLUMN fichado_por_id")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE inmobiliaria_propiedad DROP COLUMN fecha_fichado")
        except:
            pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0034_add_titulo_to_propiedad'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(
            add_fichado_por_fields,
            remove_fichado_por_fields,
        ),
    ] 