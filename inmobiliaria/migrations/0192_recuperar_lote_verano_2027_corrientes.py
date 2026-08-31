from django.db import migrations


def recuperar_verano_2027(apps, schema_editor):
    from inmobiliaria.disponibilidad_masiva_utils import recuperar_lote_corrientes_verano_2027

    recuperar_lote_corrientes_verano_2027(apps=apps, nombre='Verano 2027', min_deptos=5)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0191_lote_disponibilidad_masiva'),
    ]

    operations = [
        migrations.RunPython(recuperar_verano_2027, noop),
    ]
