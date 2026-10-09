import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0218_gastooficina_reciclable'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiquidacionProductoresCierre',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('anio', models.PositiveSmallIntegerField()),
                ('mes', models.PositiveSmallIntegerField()),
                ('cuadro', models.JSONField(default=dict)),
                ('totales_vendedores', models.JSONField(
                    default=dict,
                    help_text='vendedor_id → total liquidado (lo que usa el cierre de oficina).',
                )),
                ('fecha_cierre', models.DateTimeField(auto_now_add=True)),
                ('sucursal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='liquidaciones_productores_cerradas',
                    to='inmobiliaria.sucursal',
                )),
                ('usuario_cierre', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='liquidaciones_productores_cerradas',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Liquidación de productores cerrada',
                'verbose_name_plural': 'Liquidaciones de productores cerradas',
            },
        ),
        migrations.AddConstraint(
            model_name='liquidacionproductorescierre',
            constraint=models.UniqueConstraint(
                fields=('sucursal', 'anio', 'mes'),
                name='uniq_liq_productores_cierre_mes',
            ),
        ),
    ]
