# Quitar UNIQUE real en BD sobre dni (0001 lo creó; 0114 solo alteró el campo en el estado Django).
# Si el índice ya no existe, no falla.

from django.db import migrations


def _drop_mysql_unique_dni(cursor, table: str):
    cursor.execute(
        """
        SELECT DISTINCT INDEX_NAME FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s
          AND column_name = 'dni' AND non_unique = 0 AND seq_in_index = 1
        """,
        [table],
    )
    for (idx_name,) in cursor.fetchall():
        if not idx_name or str(idx_name).upper() == 'PRIMARY':
            continue
        cursor.execute(f"ALTER TABLE `{table}` DROP INDEX `{idx_name}`")


def _drop_postgres_unique_dni(cursor, table: str):
    cursor.execute(
        """
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_schema = kcu.constraint_schema
         AND tc.constraint_name = kcu.constraint_name
        WHERE tc.table_schema = current_schema()
          AND tc.table_name = %s
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name = 'dni'
        """,
        [table],
    )
    for (conname,) in cursor.fetchall():
        if not conname:
            continue
        cursor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{conname}" CASCADE')


def forwards_drop_unique_dni(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor
    if vendor == 'mysql':
        with connection.cursor() as cursor:
            _drop_mysql_unique_dni(cursor, 'inmobiliaria_propietario')
            _drop_mysql_unique_dni(cursor, 'inmobiliaria_inquilino')
    elif vendor == 'postgresql':
        with connection.cursor() as cursor:
            _drop_postgres_unique_dni(cursor, 'inmobiliaria_propietario')
            _drop_postgres_unique_dni(cursor, 'inmobiliaria_inquilino')


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0116_contratoalquiler_moneda'),
    ]

    operations = [
        migrations.RunPython(forwards_drop_unique_dni, backwards_noop),
    ]
