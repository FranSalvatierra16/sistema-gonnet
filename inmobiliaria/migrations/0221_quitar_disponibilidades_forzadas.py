from django.db import migrations


def quitar_forzadas(apps, schema_editor):
    Disponibilidad = apps.get_model('inmobiliaria', 'Disponibilidad')
    Disponibilidad.objects.filter(forzar_disponible=True).update(forzar_disponible=False)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0220_movimientocaja_reciclable'),
    ]

    operations = [
        migrations.RunPython(quitar_forzadas, migrations.RunPython.noop),
    ]
