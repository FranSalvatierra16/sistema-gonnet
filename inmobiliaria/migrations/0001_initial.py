# Generated by Django 4.2.7 on 2024-09-05 19:38

import django.contrib.auth.models
import django.contrib.auth.validators
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import inmobiliaria.models.persona


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
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
                ('descripcion', models.TextField(blank=True)),
                ('tipo_inmueble', models.CharField(choices=[('-', '-'), ('campo', 'Campo'), ('casa-chalet', 'Casa - Chalet'), ('departamento', 'Departamento'), ('fondo_de_comercio', 'Fondo de Comercio'), ('galpon', 'Galpon'), ('hotel', 'Hotel'), ('local', 'Local'), ('oficina', 'Oficina'), ('ph', 'PH'), ('quinta', 'Quinta'), ('terreno', 'Terreno'), ('cochera', 'Cochera'), ('edificio', 'Edificio'), ('inmueble_en_block', 'Inmueble en Block'), ('duplex', 'Dúplex'), ('emprendimiento', 'Emprendimiento'), ('cabaña', 'Cabaña'), ('casaquinta', 'Casa Quinta'), ('deposito', 'Deposito')], default='otro', max_length=20)),
                ('vista', models.CharField(choices=[('a_la_calle', 'A la calle'), ('contrafrente', 'Contrafrente'), ('lateral', 'Lateral')], default='otro', max_length=20)),
                ('piso', models.IntegerField()),
                ('ambientes', models.IntegerField()),
                ('valoracion', models.CharField(choices=[('excelente', 'Excelente'), ('muy_bueno', 'Muy bueno'), ('bueno', 'Bueno'), ('regular', 'Regular'), ('malo', 'Malo')], default='otro', max_length=20)),
                ('cuenta_bancaria', models.CharField(blank=True, help_text='Número de cuenta bancaria para depósitos', max_length=100)),
                ('precio_diario', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Precio por día')),
                ('habilitar_precio_diario', models.BooleanField(default=False, verbose_name='Habilitar precio por día')),
                ('precio_venta', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Precio por venta')),
                ('habilitar_precio_venta', models.BooleanField(default=False, verbose_name='Habilitar precio por venta')),
                ('precio_alquiler', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True, verbose_name='Precio por alquiler')),
                ('habilitar_precio_alquiler', models.BooleanField(default=False, verbose_name='Habilitar precio por alquiler')),
                ('amoblado', models.BooleanField(default=False)),
                ('cochera', models.BooleanField(default=False)),
                ('tv_smart', models.BooleanField(default=False)),
                ('wifi', models.BooleanField(default=False)),
                ('dependencia', models.BooleanField(default=False)),
                ('patio', models.BooleanField(default=False)),
                ('parrilla', models.BooleanField(default=False)),
                ('piscina', models.BooleanField(default=False)),
                ('reciclado', models.BooleanField(default=False)),
                ('a_estrenar', models.BooleanField(default=False)),
                ('terraza', models.BooleanField(default=False)),
                ('balcon', models.BooleanField(default=False)),
                ('baulera', models.BooleanField(default=False)),
                ('lavadero', models.BooleanField(default=False)),
                ('seguridad', models.BooleanField(default=False)),
                ('vista_al_Mar', models.BooleanField(default=False)),
                ('vista_panoramica', models.BooleanField(default=False)),
                ('apto_credito', models.BooleanField(default=False)),
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
            name='Reserva',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField()),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='inmobiliaria.propiedad')),
            ],
        ),
        migrations.AddField(
            model_name='propiedad',
            name='propietario',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='propiedades', to='inmobiliaria.propietario'),
        ),
        migrations.CreateModel(
            name='Disponibilidad',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('fecha_inicio', models.DateField()),
                ('fecha_fin', models.DateField()),
                ('propiedad', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='disponibilidades', to='inmobiliaria.propiedad')),
            ],
            options={
                'verbose_name': 'Disponibilidad',
                'verbose_name_plural': 'Disponibilidades',
            },
        ),
        migrations.CreateModel(
            name='Vendedor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                ('dni', models.CharField(max_length=8, unique=True, validators=[inmobiliaria.models.persona.validate_dni])),
                ('nombre', models.CharField(max_length=100)),
                ('apellido', models.CharField(max_length=100)),
                ('fecha_nacimiento', models.DateField()),
                ('email', models.EmailField(max_length=254)),
                ('comision', models.DecimalField(blank=True, decimal_places=2, help_text='Comisión en porcentaje', max_digits=5, null=True)),
                ('celular', models.CharField(blank=True, max_length=20)),
                ('nivel', models.IntegerField(choices=[(1, 'Básico'), (2, 'Intermedio'), (3, 'Avanzado'), (4, 'Administrador')], default=1, help_text='Nivel del vendedor para determinar sus permisos')),
                ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
            ],
            options={
                'verbose_name': 'Vendedor',
                'verbose_name_plural': 'Vendedores',
            },
            managers=[
                ('objects', django.contrib.auth.models.UserManager()),
            ],
        ),
        migrations.AddConstraint(
            model_name='vendedor',
            constraint=models.UniqueConstraint(fields=('dni',), name='unique_dni'),
        ),
    ]
