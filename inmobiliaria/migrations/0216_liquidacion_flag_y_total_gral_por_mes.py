import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0215_precio_estudiante_total_mensual'),
    ]

    operations = [
        migrations.CreateModel(
            name='BasicoNoSumaVigencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vigente_desde', models.DateField(help_text='Primer día del mes desde el que rige.')),
                ('activo', models.BooleanField(default=False)),
                ('vendedor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='basico_no_suma_vigencias',
                    to='inmobiliaria.vendedor',
                )),
            ],
            options={
                'verbose_name': 'Básico no suma por vigencia',
                'verbose_name_plural': 'Básico no suma por vigencia',
                'ordering': ['vendedor_id', '-vigente_desde'],
            },
        ),
        migrations.AddConstraint(
            model_name='basiconosumavigencia',
            constraint=models.UniqueConstraint(
                fields=('vendedor', 'vigente_desde'),
                name='uniq_basico_no_suma_vigencia_vendedor_desde',
            ),
        ),
        migrations.AddField(
            model_name='cuadrohonorariostotalgral',
            name='vigente_desde',
            field=models.DateField(blank=True, null=True),
        ),
    ]
