from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0120_caja_arqueo_cierre'),
    ]

    operations = [
        migrations.CreateModel(
            name='CajaArqueoManual',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('efectivo', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('cheque', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('tarjeta', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('dolares', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('deposito_galicia', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('deposito_mp', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ('cuentas_json', models.JSONField(blank=True, default=dict)),
                ('fecha_registro', models.DateTimeField(auto_now_add=True)),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('caja', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='arqueo_manual', to='inmobiliaria.caja')),
                ('registrado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='arqueos_manuales_caja', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Arqueo manual de caja',
                'verbose_name_plural': 'Arqueos manuales de caja',
                'db_table': 'inmobiliaria_caja_arqueo_manual',
            },
        ),
    ]
