from django.db import migrations, models
import django.db.models.deletion


def migrar_vendedores_a_productores(apps, schema_editor):
    OperacionProductor = apps.get_model('inmobiliaria', 'OperacionProductor')
    Reserva = apps.get_model('inmobiliaria', 'Reserva')
    ContratoAlquiler = apps.get_model('inmobiliaria', 'ContratoAlquiler')

    for reserva in Reserva.objects.filter(vendedor_id__isnull=False).iterator():
        OperacionProductor.objects.get_or_create(
            reserva_id=reserva.id,
            vendedor_id=reserva.vendedor_id,
            defaults={'orden': 0},
        )
    for contrato in ContratoAlquiler.objects.filter(vendedor_id__isnull=False).iterator():
        OperacionProductor.objects.get_or_create(
            contrato_id=contrato.id,
            vendedor_id=contrato.vendedor_id,
            defaults={'orden': 0},
        )


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0148_contrato_comisiones_caratula'),
    ]

    operations = [
        migrations.CreateModel(
            name='OperacionProductor',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('orden', models.PositiveSmallIntegerField(default=0)),
                (
                    'contrato',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='productores_operacion',
                        to='inmobiliaria.contratoalquiler',
                    ),
                ),
                (
                    'reserva',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='productores_operacion',
                        to='inmobiliaria.reserva',
                    ),
                ),
                (
                    'vendedor',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='operaciones_como_productor',
                        to='inmobiliaria.vendedor',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Productor de operación',
                'verbose_name_plural': 'Productores de operación',
                'ordering': ['orden', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='operacionproductor',
            constraint=models.UniqueConstraint(
                condition=models.Q(('reserva__isnull', False)),
                fields=('reserva', 'vendedor'),
                name='uniq_operacion_productor_reserva',
            ),
        ),
        migrations.AddConstraint(
            model_name='operacionproductor',
            constraint=models.UniqueConstraint(
                condition=models.Q(('contrato__isnull', False)),
                fields=('contrato', 'vendedor'),
                name='uniq_operacion_productor_contrato',
            ),
        ),
        migrations.RunPython(migrar_vendedores_a_productores, migrations.RunPython.noop),
    ]
