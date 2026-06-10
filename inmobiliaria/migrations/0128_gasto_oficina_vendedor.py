from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0127_oficina_gastos_categorias'),
    ]

    operations = [
        migrations.AddField(
            model_name='gastooficina',
            name='vendedor',
            field=models.ForeignKey(
                blank=True,
                help_text='Obligatorio para sueldos a productores.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='gastos_oficina_sueldo',
                to='inmobiliaria.vendedor',
                verbose_name='Productor / vendedor',
            ),
        ),
    ]
