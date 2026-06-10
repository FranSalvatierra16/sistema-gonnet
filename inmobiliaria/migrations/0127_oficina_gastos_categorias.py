from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0126_vale_beneficiario_otro'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CategoriaGastoOficina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('activa', models.BooleanField(default=True)),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='subcategorias', to='inmobiliaria.categoriagastooficina', verbose_name='Categoría padre')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='categorias_gasto_oficina', to='inmobiliaria.sucursal')),
            ],
            options={
                'verbose_name': 'Categoría gasto oficina',
                'verbose_name_plural': 'Categorías gasto oficina',
                'ordering': ['orden', 'nombre'],
            },
        ),
        migrations.CreateModel(
            name='GastoOficina',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha', models.DateField()),
                ('monto', models.DecimalField(decimal_places=2, max_digits=14)),
                ('descripcion', models.CharField(max_length=255)),
                ('observaciones', models.TextField(blank=True)),
                ('fecha_creacion', models.DateTimeField(auto_now_add=True)),
                ('fecha_modificacion', models.DateTimeField(auto_now=True)),
                ('categoria', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='gastos', to='inmobiliaria.categoriagastooficina', verbose_name='Categoría / subcategoría')),
                ('movimiento_caja', models.ForeignKey(blank=True, help_text='Opcional: egreso de caja que pagó este gasto.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gastos_oficina_vinculados', to='inmobiliaria.movimientocaja')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='gastos_oficina', to='inmobiliaria.sucursal')),
                ('usuario_creacion', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='gastos_oficina_creados', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Gasto de oficina',
                'verbose_name_plural': 'Gastos de oficina',
                'ordering': ['-fecha', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='categoriagastooficina',
            constraint=models.UniqueConstraint(fields=('sucursal', 'parent', 'nombre'), name='uniq_categoria_gasto_oficina_sucursal_parent_nombre'),
        ),
    ]
