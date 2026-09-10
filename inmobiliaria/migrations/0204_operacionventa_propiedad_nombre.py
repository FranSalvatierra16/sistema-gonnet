# Propiedad de venta como texto libre (sin FK obligatoria)

from django.db import migrations, models
import django.db.models.deletion


def rellenar_propiedad_nombre(apps, schema_editor):
    OperacionVenta = apps.get_model('inmobiliaria', 'OperacionVenta')
    Propiedad = apps.get_model('inmobiliaria', 'Propiedad')
    for op in OperacionVenta.objects.filter(propiedad_id__isnull=False).iterator():
        if (op.propiedad_nombre or '').strip():
            continue
        try:
            prop = Propiedad.objects.get(pk=op.propiedad_id)
        except Propiedad.DoesNotExist:
            op.propiedad_nombre = f'#{op.propiedad_id}'
            op.save(update_fields=['propiedad_nombre'])
            continue
        partes = [f'#{prop.id}', '—', (prop.direccion or '').strip() or 'Sin dirección']
        piso = (getattr(prop, 'piso', None) or '').strip()
        depto = (getattr(prop, 'departamento', None) or '').strip()
        if piso or depto:
            ud = ' '.join(x for x in [f'{piso}°' if piso else '', depto] if x).strip()
            if ud:
                partes.append(f'· {ud}')
        op.propiedad_nombre = ' '.join(partes)[:255]
        op.save(update_fields=['propiedad_nombre'])


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0203_cuadro_honorarios_total_gral_categoria'),
    ]

    operations = [
        migrations.AddField(
            model_name='operacionventa',
            name='propiedad_nombre',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Nombre o descripción libre de lo vendido (sin ficha).',
                max_length=255,
                verbose_name='Propiedad',
            ),
        ),
        migrations.AlterField(
            model_name='operacionventa',
            name='propiedad',
            field=models.ForeignKey(
                blank=True,
                help_text='Opcional / legado. Las ventas nuevas no vinculan ficha.',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='operaciones_venta',
                to='inmobiliaria.propiedad',
                verbose_name='Propiedad (ficha)',
            ),
        ),
        migrations.RunPython(rellenar_propiedad_nombre, migrations.RunPython.noop),
    ]
