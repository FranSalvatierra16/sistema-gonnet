from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0204_operacionventa_propiedad_nombre'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReporteDeptosOficinaPreferencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('oculto', models.BooleanField(default=False)),
                ('forzado', models.BooleanField(default=False)),
                ('propiedad', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='prefs_reporte_deptos_oficina',
                    to='inmobiliaria.propiedad',
                )),
                ('sucursal', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='prefs_reporte_deptos_oficina',
                    to='inmobiliaria.sucursal',
                )),
            ],
            options={
                'verbose_name': 'Preferencia depto en reporte oficina',
                'verbose_name_plural': 'Preferencias depto en reporte oficina',
            },
        ),
        migrations.AddConstraint(
            model_name='reportedeptosoficinapreferencia',
            constraint=models.UniqueConstraint(
                fields=('sucursal', 'propiedad'),
                name='uniq_pref_reporte_deptos_oficina_suc_prop',
            ),
        ),
    ]
