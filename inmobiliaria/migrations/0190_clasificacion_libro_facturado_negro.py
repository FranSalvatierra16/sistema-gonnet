# Generated manually — facturado / en negro en libro de oficina (Gery 1759)

from django.db import migrations, models
from django.db.models import Q


def activar_gery_1759(apps, schema_editor):
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    Propiedad.objects.filter(pk='1759').update(libro_exige_facturado_negro=True)
    # Fallback por dirección/piso si el id no coincide en algún entorno
    Propiedad.objects.filter(
        libro_exige_facturado_negro=False,
        piso__iexact='12',
    ).filter(
        Q(direccion__icontains='gery')
        | Q(direccion__icontains='1759')
        | Q(titulo__icontains='gery')
    ).update(libro_exige_facturado_negro=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0189_operacionventa_honorarios_usd_libro'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='libro_exige_facturado_negro',
            field=models.BooleanField(
                default=False,
                help_text='Al cargar movimientos de caja de esta propiedad, obliga a elegir Facturado o En negro.',
                verbose_name='Libro: exigir facturado / en negro',
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='clasificacion_libro',
            field=models.CharField(
                blank=True,
                choices=[('facturado', 'Facturado'), ('negro', 'En negro')],
                db_index=True,
                default='',
                help_text='Solo para propiedades que exigen esta clasificación en el libro de oficina.',
                max_length=20,
                verbose_name='Clasificación libro (facturado / en negro)',
            ),
        ),
        migrations.AddField(
            model_name='filamanuallibropropiedad',
            name='clasificacion_libro',
            field=models.CharField(
                blank=True,
                choices=[('facturado', 'Facturado'), ('negro', 'En negro')],
                db_index=True,
                default='',
                max_length=20,
                verbose_name='Clasificación libro (facturado / en negro)',
            ),
        ),
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='clasificacion_libro',
            field=models.CharField(
                blank=True,
                choices=[('facturado', 'Facturado'), ('negro', 'En negro')],
                db_index=True,
                default='',
                max_length=20,
                verbose_name='Clasificación libro (facturado / en negro)',
            ),
        ),
        migrations.RunPython(activar_gery_1759, noop_reverse),
    ]
