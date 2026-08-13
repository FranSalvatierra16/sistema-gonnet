# Generated manually for portal web

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0177_cuentabancaria_fecha_saldo_inicial'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='publicar_web',
            field=models.BooleanField(
                default=False,
                help_text='Si está marcado, la propiedad puede aparecer en el portal público (/web/).',
                verbose_name='Publicar en web',
            ),
        ),
        migrations.AddField(
            model_name='propiedad',
            name='destacada_web',
            field=models.BooleanField(
                default=False,
                help_text='Aparece en el carrusel de propiedades destacadas del portal público.',
                verbose_name='Destacada en web',
            ),
        ),
        migrations.CreateModel(
            name='ConsultaWeb',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(max_length=120)),
                ('email', models.EmailField(blank=True, default='', max_length=254)),
                ('telefono', models.CharField(blank=True, default='', max_length=40)),
                ('mensaje', models.TextField(blank=True, default='')),
                ('fecha_desde', models.DateField(blank=True, null=True)),
                ('fecha_hasta', models.DateField(blank=True, null=True)),
                ('ficha', models.CharField(blank=True, default='', max_length=64)),
                ('sucursal_preferida', models.CharField(blank=True, default='', max_length=80)),
                ('ambientes', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('tipo_operacion', models.CharField(blank=True, default='alquiler_temporario', max_length=40)),
                ('estado', models.CharField(
                    choices=[('nueva', 'Nueva'), ('contactada', 'Contactada'), ('cerrada', 'Cerrada')],
                    default='nueva',
                    max_length=20,
                )),
                ('creado_en', models.DateTimeField(default=django.utils.timezone.now)),
                ('notas_internas', models.TextField(blank=True, default='')),
                ('propiedad', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='consultas_web',
                    to='inmobiliaria.propiedad',
                )),
            ],
            options={
                'verbose_name': 'Consulta web',
                'verbose_name_plural': 'Consultas web',
                'ordering': ['-creado_en'],
            },
        ),
    ]
