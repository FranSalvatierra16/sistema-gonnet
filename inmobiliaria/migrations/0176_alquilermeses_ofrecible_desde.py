from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0175_caja_cotizacion_dolar'),
    ]

    operations = [
        migrations.AddField(
            model_name='alquilermeses',
            name='ofrecible_desde',
            field=models.DateField(
                blank=True,
                help_text='Si hay contrato vigente (ocupado/reservado), fecha a partir de la cual se puede ofrecer un nuevo alquiler.',
                null=True,
                verbose_name='Ofrecible desde',
            ),
        ),
    ]
