# Generated by Django 4.2.7 on 2024-12-26 12:38

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0022_alter_imagenpropiedad_propiedad'),
    ]

    operations = [
        migrations.AddField(
            model_name='propiedad',
            name='fecha_fichado',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Fecha de fichado'),
        ),
        migrations.AddField(
            model_name='propiedad',
            name='fichado_por',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='propiedades_fichadas', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='VentaPropiedad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('en_venta', models.BooleanField(default=False, verbose_name='Disponible para venta')),
                ('precio_venta', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Precio de venta')),
                ('precio_autorizacion', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True, verbose_name='Precio de autorización')),
                ('estado', models.CharField(choices=[('disponible', 'Disponible'), ('reservado', 'Reservado'), ('vendido', 'Vendido')], default='disponible', max_length=20, verbose_name='Estado de la venta')),
                ('precio_expensas', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Precio de expensas')),
                ('escribania', models.TextField(blank=True, verbose_name='Información de escribanía')),
                ('observaciones', models.TextField(blank=True, verbose_name='Observaciones')),
                ('fecha_actualizacion', models.DateTimeField(auto_now=True)),
                ('propiedad', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='info_venta', to='inmobiliaria.propiedad')),
            ],
        ),
    ]
