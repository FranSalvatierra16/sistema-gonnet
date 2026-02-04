# Corrige la secuencia de id de VentaPropiedad cuando queda desincronizada (duplicate key id=9)
# Ejecutar: python manage.py migrate inmobiliaria 0075_fix_ventapropiedad_id_sequence

from django.db import migrations


def fix_ventapropiedad_sequence(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT setval(
                pg_get_serial_sequence('inmobiliaria_ventapropiedad', 'id'),
                COALESCE((SELECT MAX(id) FROM inmobiliaria_ventapropiedad), 1)
            );
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0074_alter_precio_ajuste_porcentaje_max_digits'),
    ]

    operations = [
        migrations.RunPython(fix_ventapropiedad_sequence, noop),
    ]
