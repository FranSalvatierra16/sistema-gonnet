from django.db import migrations

def remove_llave_index(apps, schema_editor):
    """
    Eliminar índice 'llave' de forma compatible con MySQL y PostgreSQL
    """
    if schema_editor.connection.vendor == 'mysql':
        schema_editor.execute('ALTER TABLE inmobiliaria_propiedad DROP INDEX llave;')
    elif schema_editor.connection.vendor == 'postgresql':
        # En PostgreSQL, primero verificar si existe la constraint
        schema_editor.execute("""
            DO $$ 
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint 
                    WHERE conname = 'llave' 
                    AND conrelid = 'inmobiliaria_propiedad'::regclass
                ) THEN
                    ALTER TABLE inmobiliaria_propiedad DROP CONSTRAINT llave;
                END IF;
            END $$;
        """)

def add_llave_index(apps, schema_editor):
    """
    Restaurar índice 'llave' (reverse operation)
    """
    schema_editor.execute('ALTER TABLE inmobiliaria_propiedad ADD UNIQUE (llave);')

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0008_alter_propiedad_numero_por_propietario'),
    ]

    operations = [
        migrations.RunPython(remove_llave_index, reverse_code=add_llave_index),
    ] 