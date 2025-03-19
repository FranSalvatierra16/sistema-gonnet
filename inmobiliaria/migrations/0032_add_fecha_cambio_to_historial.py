from django.db import migrations, models
import django.utils.timezone

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0031_recreate_caja_table'),  # Asegúrate que este número sea correcto
    ]

    operations = [
        migrations.RunSQL(
            """
            ALTER TABLE inmobiliaria_historialdisponibilidad
            ADD COLUMN fecha_cambio datetime(6) NOT NULL DEFAULT CURRENT_TIMESTAMP;
            """,
            reverse_sql="""
            ALTER TABLE inmobiliaria_historialdisponibilidad
            DROP COLUMN fecha_cambio;
            """
        )
    ] 