# Carrera por inquilino: through model ContratoInquilino

from django.db import migrations, models


def migrar_inquilinos_a_through(apps, schema_editor):
    ContratoAlquiler = apps.get_model('inmobiliaria', 'ContratoAlquiler')
    ContratoInquilino = apps.get_model('inmobiliaria', 'ContratoInquilino')
    for c in ContratoAlquiler.objects.all():
        inqs = list(c.inquilinos.all())
        if not inqs:
            ContratoInquilino.objects.get_or_create(
                contrato=c, inquilino=c.inquilino,
                defaults={'carrera': c.carrera or ''}
            )
        else:
            for inq in inqs:
                ContratoInquilino.objects.get_or_create(
                    contrato=c, inquilino=inq,
                    defaults={'carrera': c.carrera or ''}
                )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0083_contratoalquiler_inquilinos'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContratoInquilino',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('carrera', models.CharField(blank=True, max_length=200, verbose_name='Carrera del inquilino')),
                ('contrato', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='contrato_inquilinos', to='inmobiliaria.contratoalquiler')),
                ('inquilino', models.ForeignKey(on_delete=models.deletion.CASCADE, related_name='contrato_inquilino_set', to='inmobiliaria.inquilino')),
            ],
            options={
                'ordering': ['contrato', 'id'],
                'unique_together': {('contrato', 'inquilino')},
            },
        ),
        migrations.RunPython(migrar_inquilinos_a_through, reverse_noop),
        migrations.RemoveField(
            model_name='contratoalquiler',
            name='inquilinos',
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='inquilinos',
            field=models.ManyToManyField(
                blank=True,
                help_text='Todos los inquilinos del contrato',
                related_name='contratos_como_inquilino',
                through='inmobiliaria.ContratoInquilino',
                to='inmobiliaria.inquilino',
                verbose_name='Inquilinos',
            ),
        ),
    ]
