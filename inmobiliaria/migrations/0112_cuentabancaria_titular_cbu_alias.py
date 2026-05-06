# Generated manually

from django.db import migrations, models


def forwards_backfill_cuenta_bancaria(apps, schema_editor):
    CuentaBancaria = apps.get_model('inmobiliaria', 'CuentaBancaria')
    for c in CuentaBancaria.objects.all():
        titular = (getattr(c, 'titular', None) or '').strip()
        alias = (c.alias or '').strip()
        numero = (c.numero_cuenta or '').strip()
        if not titular:
            c.titular = 'Sin especificar'
        if not alias:
            c.alias = numero if numero else 'PENDIENTE'
        c.save()


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0111_movimientocaja_monto_dolares'),
    ]

    operations = [
        migrations.AddField(
            model_name='cuentabancaria',
            name='titular',
            field=models.CharField(default='', help_text='Titular de la cuenta', max_length=200),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='numero_cuenta',
            field=models.CharField(
                blank=True,
                help_text='Número de cuenta (opcional, solo referencia)',
                max_length=50,
            ),
        ),
        migrations.RunPython(forwards_backfill_cuenta_bancaria, backwards_noop),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='alias',
            field=models.CharField(
                help_text='CBU, CVU o alias para transferencias (ej: 22 dígitos o MI.ALIAS.MP)',
                max_length=100,
            ),
        ),
        migrations.AlterField(
            model_name='cuentabancaria',
            name='titular',
            field=models.CharField(help_text='Titular de la cuenta', max_length=200),
        ),
    ]
