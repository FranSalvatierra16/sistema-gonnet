from decimal import Decimal

import django.core.validators
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0122_movimiento_caja_imputacion_corresponde'),
    ]

    operations = [
        migrations.CreateModel(
            name='CarteraPropiedadUsuario',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('porcentaje', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('100'),
                    help_text='Porcentaje de ganancias y gastos de oficina que te corresponden.',
                    max_digits=5,
                    validators=[
                        django.core.validators.MinValueValidator(Decimal('0.01')),
                        django.core.validators.MaxValueValidator(Decimal('100')),
                    ],
                )),
                ('fecha_alta', models.DateTimeField(auto_now_add=True)),
                ('inquilino', models.ForeignKey(
                    blank=True,
                    help_text='Inquilino usado al agregar la propiedad (referencia).',
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='carteras_por_inquilino',
                    to='inmobiliaria.inquilino',
                )),
                ('propiedad', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='en_carteras_usuario',
                    to='inmobiliaria.propiedad',
                )),
                ('usuario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='cartera_propiedades',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Propiedad en mi cartera',
                'verbose_name_plural': 'Mis propiedades',
                'db_table': 'inmobiliaria_cartera_propiedad_usuario',
                'ordering': ['-fecha_alta'],
            },
        ),
        migrations.AddConstraint(
            model_name='carterapropiedadusuario',
            constraint=models.UniqueConstraint(
                fields=('usuario', 'propiedad'),
                name='uniq_cartera_usuario_propiedad',
            ),
        ),
    ]
