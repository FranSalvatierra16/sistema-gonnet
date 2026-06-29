from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0142_liquidacion_gasto_moneda'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='liq_monto_propietario',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Override manual desde carátula antes de liquidar.',
                max_digits=12,
                null=True,
                verbose_name='Monto propietario (liquidación)',
            ),
        ),
        migrations.AddField(
            model_name='reserva',
            name='liq_monto_inmobiliaria',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Override manual desde carátula antes de liquidar.',
                max_digits=12,
                null=True,
                verbose_name='Monto inmobiliaria (liquidación)',
            ),
        ),
        migrations.AddField(
            model_name='reserva',
            name='liq_monto_cochera',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name='Monto cochera (liquidación)',
            ),
        ),
        migrations.AddField(
            model_name='reserva',
            name='liq_monto_fondo',
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
                verbose_name='Fondo mantenimiento (liquidación)',
            ),
        ),
    ]
