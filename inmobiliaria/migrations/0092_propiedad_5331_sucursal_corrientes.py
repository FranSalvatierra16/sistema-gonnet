# Cambio puntual: propiedad 5331 de sucursal Colon -> Corrientes

from django.db import migrations


def forwards(apps, schema_editor):
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    try:
        corrientes = Sucursal.objects.get(nombre='Corrientes')
    except Sucursal.DoesNotExist:
        return
    try:
        p = Propiedad.objects.get(pk=5331)
    except Propiedad.DoesNotExist:
        return
    if p.sucursal_id != corrientes.pk:
        p.sucursal_id = corrientes.pk
        p.save(update_fields=['sucursal_id'])


def backwards(apps, schema_editor):
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    try:
        colon = Sucursal.objects.get(nombre='Colon')
    except Sucursal.DoesNotExist:
        return
    try:
        p = Propiedad.objects.get(pk=5331)
    except Propiedad.DoesNotExist:
        return
    if p.sucursal_id == colon.pk:
        return
    p.sucursal_id = colon.pk
    p.save(update_fields=['sucursal_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0091_merge_0090_branches'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
