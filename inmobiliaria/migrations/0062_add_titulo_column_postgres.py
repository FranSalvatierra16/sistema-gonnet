from django.db import migrations


def add_titulo_column(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE inmobiliaria_propiedad
            ADD COLUMN IF NOT EXISTS titulo varchar(255) NULL
            """
        )


def remove_titulo_column(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return

    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            ALTER TABLE inmobiliaria_propiedad
            DROP COLUMN IF EXISTS titulo
            """
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0061_caja_id_propiedad_titulo_alter_caja_numero_and_more'),
    ]

    operations = [
        migrations.RunPython(add_titulo_column, reverse_code=remove_titulo_column),
    ]

