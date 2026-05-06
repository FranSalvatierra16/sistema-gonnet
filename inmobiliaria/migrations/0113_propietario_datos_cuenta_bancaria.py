# Generated manually

from django.db import migrations, models


def forwards_propietario_cuenta(apps, schema_editor):
    Propietario = apps.get_model('inmobiliaria', 'Propietario')
    for p in Propietario.objects.all():
        legacy = (p.cuenta_bancaria or '').strip()
        cbu = (getattr(p, 'cuenta_cbu_alias', None) or '').strip()
        if legacy and not cbu:
            p.cuenta_cbu_alias = legacy[:100]
        b = (p.cuenta_banco or '').strip()
        t = (p.cuenta_titular or '').strip()
        c = (p.cuenta_cbu_alias or '').strip()
        n = (p.cuenta_numero or '').strip()
        parts = []
        if b:
            parts.append(f'Banco: {b}')
        if t:
            parts.append(f'Titular: {t}')
        if c:
            parts.append(f'CBU/Alias: {c}')
        if n:
            parts.append(f'Cuenta: {n}')
        p.cuenta_bancaria = ' · '.join(parts)[:500] if parts else ''
        p.save()


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0112_cuentabancaria_titular_cbu_alias'),
    ]

    operations = [
        migrations.AddField(
            model_name='propietario',
            name='cuenta_banco',
            field=models.CharField(blank=True, help_text='Nombre del banco o billetera', max_length=100),
        ),
        migrations.AddField(
            model_name='propietario',
            name='cuenta_titular',
            field=models.CharField(blank=True, help_text='Titular de la cuenta', max_length=200),
        ),
        migrations.AddField(
            model_name='propietario',
            name='cuenta_cbu_alias',
            field=models.CharField(blank=True, help_text='CBU, CVU o alias para transferencias', max_length=100),
        ),
        migrations.AddField(
            model_name='propietario',
            name='cuenta_numero',
            field=models.CharField(blank=True, help_text='Número de cuenta (opcional, referencia)', max_length=50),
        ),
        migrations.AlterField(
            model_name='propietario',
            name='cuenta_bancaria',
            field=models.CharField(
                blank=True,
                help_text='Resumen automático (banco, titular, CBU/alias, cuenta) para listados e integraciones',
                max_length=500,
            ),
        ),
        migrations.RunPython(forwards_propietario_cuenta, backwards_noop),
    ]
