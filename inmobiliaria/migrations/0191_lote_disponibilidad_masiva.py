# Generated manually — lotes de disponibilidad masiva (nombre + historial + repetir)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0190_clasificacion_libro_facturado_negro'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoteDisponibilidadMasiva',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nombre', models.CharField(help_text='Ej.: Verano 2027, Invierno julio 2026', max_length=200, verbose_name='Nombre')),
                ('fecha_inicio', models.DateField(verbose_name='Fecha inicio')),
                ('fecha_fin', models.DateField(verbose_name='Fecha fin')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('cantidad_creadas', models.PositiveIntegerField(default=0)),
                ('cantidad_errores', models.PositiveIntegerField(default=0)),
                ('notas', models.TextField(blank=True, default='')),
                ('creado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='lotes_disponibilidad_masiva_creados',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('propiedades', models.ManyToManyField(
                    blank=True,
                    related_name='lotes_disponibilidad_masiva',
                    to='inmobiliaria.propiedad',
                    verbose_name='Departamentos incluidos',
                )),
                ('repetido_desde', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='repeticiones',
                    to='inmobiliaria.lotedisponibilidadmasiva',
                    verbose_name='Repetido desde',
                )),
                ('sucursal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='lotes_disponibilidad_masiva',
                    to='inmobiliaria.sucursal',
                )),
            ],
            options={
                'verbose_name': 'Lote disponibilidad masiva',
                'verbose_name_plural': 'Lotes disponibilidad masiva',
                'ordering': ['-creado_en', '-id'],
            },
        ),
    ]
