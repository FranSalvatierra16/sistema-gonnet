from django.db import migrations, models
import django.db.models.deletion


def aplicar_estructura_cierre_corrientes(apps, schema_editor):
    Sucursal = apps.get_model('inmobiliaria', 'Sucursal')
    from inmobiliaria.oficina_gastos import asegurar_estructura_cierre_oficina

    for sucursal in Sucursal.objects.all():
        asegurar_estructura_cierre_oficina(sucursal)


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0131_movimientocaja_fecha_editable'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriagastooficina',
            name='vendedor',
            field=models.ForeignKey(
                blank=True,
                help_text='Subcategorías de Sueldos, Vales o Comisiones generadas por vendedor.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='categorias_gasto_oficina',
                to='inmobiliaria.vendedor',
                verbose_name='Vendedor vinculado',
            ),
        ),
        migrations.RunPython(aplicar_estructura_cierre_corrientes, migrations.RunPython.noop),
    ]
