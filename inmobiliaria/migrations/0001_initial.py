# Generated by Django 4.2.7 on 2024-08-28 13:57

import django.core.validators
from django.db import migrations, models
import inmobiliaria.models.persona


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Inquilino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dni', models.CharField(max_length=8, unique=True, validators=[inmobiliaria.models.persona.validate_dni])),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('fecha_nacimiento', models.DateField()),
                ('email', models.EmailField(max_length=254)),
                ('celular', models.CharField(max_length=20)),
                ('observaciones', models.TextField(blank=True)),
                ('localidad', models.CharField(max_length=100)),
                ('provincia', models.CharField(max_length=100)),
                ('domicilio', models.CharField(max_length=100)),
                ('codigo_postal', models.CharField(max_length=10)),
                ('cuit', models.CharField(max_length=11, validators=[django.core.validators.RegexValidator(message='CUIT debe tener 11 dígitos', regex='^\\d{11}$')])),
                ('tipo_ins', models.CharField(choices=[('csfl', 'CSFL'), ('exen', 'EXEN'), ('rins', 'RINS'), ('rnin', 'RNIN'), ('otro', 'Otro')], default='otro', max_length=4)),
                ('tipo_doc', models.CharField(choices=[('dni', 'DNI'), ('le', 'LE'), ('ls', 'LS'), ('cipf', 'CIPF'), ('pas', 'PAS')], default='otro', max_length=4)),
                ('garantia', models.TextField(blank=True, help_text='Información sobre la garantía del inquilino')),
            ],
            options={
                'verbose_name': 'Inquilino',
                'verbose_name_plural': 'Inquilinos',
            },
        ),
        migrations.CreateModel(
            name='Propiedad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direccion', models.CharField(max_length=255)),
                ('precio_tipo', models.CharField(choices=[('diario', 'Por día'), ('venta', 'Por venta'), ('alquiler', 'Por alquiler')], max_length=10)),
                ('precio', models.DecimalField(decimal_places=2, max_digits=10)),
                ('descripcion', models.TextField(blank=True)),
                ('vista', models.BooleanField(default=False)),
                ('piso', models.IntegerField()),
                ('ambientes', models.IntegerField()),
                ('cuenta_bancaria', models.CharField(blank=True, help_text='Número de cuenta bancaria para depósitos', max_length=100)),
            ],
            options={
                'verbose_name': 'Propiedad',
                'verbose_name_plural': 'Propiedades',
            },
        ),
        migrations.CreateModel(
            name='Propietario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dni', models.CharField(max_length=8, unique=True, validators=[inmobiliaria.models.persona.validate_dni])),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('fecha_nacimiento', models.DateField()),
                ('email', models.EmailField(max_length=254)),
                ('celular', models.CharField(max_length=20)),
                ('observaciones', models.TextField(blank=True)),
                ('localidad', models.CharField(max_length=100)),
                ('provincia', models.CharField(max_length=100)),
                ('domicilio', models.CharField(max_length=100)),
                ('codigo_postal', models.CharField(max_length=10)),
                ('cuit', models.CharField(max_length=11, validators=[django.core.validators.RegexValidator(message='CUIT debe tener 11 dígitos', regex='^\\d{11}$')])),
                ('tipo_ins', models.CharField(choices=[('csfl', 'CSFL'), ('exen', 'EXEN'), ('rins', 'RINS'), ('rnin', 'RNIN'), ('otro', 'Otro')], default='otro', max_length=4)),
                ('tipo_doc', models.CharField(choices=[('dni', 'DNI'), ('le', 'LE'), ('ls', 'LS'), ('cipf', 'CIPF'), ('pas', 'PAS')], default='otro', max_length=4)),
                ('cuenta_bancaria', models.CharField(blank=True, help_text='Número de cuenta bancaria para depósitos', max_length=100)),
            ],
            options={
                'verbose_name': 'Propietario',
                'verbose_name_plural': 'Propietarios',
            },
        ),
        migrations.CreateModel(
            name='Vendedor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dni', models.CharField(max_length=8, unique=True, validators=[inmobiliaria.models.persona.validate_dni])),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('fecha_nacimiento', models.DateField()),
                ('email', models.EmailField(max_length=254)),
                ('celular', models.CharField(max_length=20)),
                ('observaciones', models.TextField(blank=True)),
                ('localidad', models.CharField(max_length=100)),
                ('provincia', models.CharField(max_length=100)),
                ('domicilio', models.CharField(max_length=100)),
                ('codigo_postal', models.CharField(max_length=10)),
                ('cuit', models.CharField(max_length=11, validators=[django.core.validators.RegexValidator(message='CUIT debe tener 11 dígitos', regex='^\\d{11}$')])),
                ('tipo_ins', models.CharField(choices=[('csfl', 'CSFL'), ('exen', 'EXEN'), ('rins', 'RINS'), ('rnin', 'RNIN'), ('otro', 'Otro')], default='otro', max_length=4)),
                ('tipo_doc', models.CharField(choices=[('dni', 'DNI'), ('le', 'LE'), ('ls', 'LS'), ('cipf', 'CIPF'), ('pas', 'PAS')], default='otro', max_length=4)),
                ('comision', models.DecimalField(decimal_places=2, help_text='Comisión en porcentaje', max_digits=5)),
            ],
            options={
                'verbose_name': 'Vendedor',
                'verbose_name_plural': 'Vendedores',
            },
        ),
    ]
