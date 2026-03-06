# Corrige la secuencia de id de AlquilerMeses cuando queda desincronizada (duplicate key)
# Ejecutar: python manage.py migrate inmobiliaria 0085_fix_alquilermeses_id_sequence

from django.db import migrations


def fix_alquilermeses_sequence(apps, schema_editor):
    from django.db import connection
    if connection.vendor != 'postgresql':
        return
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT setval(
                pg_get_serial_sequence('inmobiliaria_alquilermeses', 'id'),
                COALESCE((SELECT MAX(id) FROM inmobiliaria_alquilermeses), 1)
            );
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0084_contratoinquilino_carrera_por_inquilino'),
    ]

    operations = [
        migrations.RunPython(fix_alquilermeses_sequence, noop),
    ]
