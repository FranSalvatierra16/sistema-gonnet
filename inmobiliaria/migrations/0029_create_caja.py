from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0028_your_previous_migration'),  # Ajusta este número
    ]

    operations = [
        migrations.CreateModel(
            name='Caja',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_apertura', models.DateTimeField(auto_now_add=True)),
                ('fecha_cierre', models.DateTimeField(blank=True, null=True)),
                ('saldo_inicial', models.DecimalField(decimal_places=2, max_digits=10)),
                ('saldo_final', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('estado', models.CharField(choices=[('abierta', 'Abierta'), ('cerrada', 'Cerrada')], default='abierta', max_length=10)),
                ('observaciones', models.TextField(blank=True)),
                ('empleado_apertura', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cajas_abiertas', to='auth.user')),
                ('empleado_cierre', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='cajas_cerradas', to='auth.user')),
                ('sucursal', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='cajas', to='inmobiliaria.sucursal')),
            ],
        ),
    ] 