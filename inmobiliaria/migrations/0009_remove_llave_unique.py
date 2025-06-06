from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0008_alter_propiedad_numero_por_propietario'),
    ]

    operations = [
        migrations.RunSQL(
            sql='ALTER TABLE inmobiliaria_propiedad DROP INDEX llave;',
            reverse_sql='ALTER TABLE inmobiliaria_propiedad ADD UNIQUE (llave);'
        ),
    ] 