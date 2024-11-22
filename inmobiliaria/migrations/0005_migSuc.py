from django.db import migrations

def forward_func(apps, schema_editor):
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    for reserva in Reserva.objects.all():
        if reserva.propiedad and reserva.propiedad.sucursal:
            reserva.sucursal = reserva.propiedad.sucursal
            reserva.save()

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0004_reserva_sucursal'),  # Reemplaza con el número de tu migración anterior
    ]

    operations = [
        migrations.RunPython(forward_func, migrations.RunPython.noop),
    ]