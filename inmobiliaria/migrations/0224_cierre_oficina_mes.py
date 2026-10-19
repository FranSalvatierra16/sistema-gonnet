from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0223_ajuste_liquidacion_productor_mes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CierreOficinaMes',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.PositiveSmallIntegerField()),
                ('mes', models.PositiveSmallIntegerField()),
                ('resumen', models.JSONField(default=dict)),
                ('reporte_deptos', models.JSONField(default=dict)),
                ('fecha_cierre', models.DateTimeField(auto_now_add=True)),
                (
                    'sucursal',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='cierres_oficina_mes',
                        to='inmobiliaria.sucursal',
                    ),
                ),
                (
                    'usuario_cierre',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='cierres_oficina_mes',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'Cierre mensual de oficina',
                'verbose_name_plural': 'Cierres mensuales de oficina',
            },
        ),
        migrations.AddConstraint(
            model_name='cierreoficinames',
            constraint=models.UniqueConstraint(
                fields=('sucursal', 'anio', 'mes'),
                name='uniq_cierre_oficina_mes',
            ),
        ),
    ]
