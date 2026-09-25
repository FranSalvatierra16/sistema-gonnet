from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def backfill_monto_cobrado(apps, schema_editor):
    ObservacionCobroInquilino = apps.get_model('inmobiliaria', 'ObservacionCobroInquilino')
    ObservacionCobroInquilino.objects.filter(estado='cobrado').update(monto_cobrado=F('monto'))


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0206_categoria_gasto_oficina_eliminada'),
    ]

    operations = [
        migrations.AddField(
            model_name='observacioncobroinquilino',
            name='monto_cobrado',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0'),
                help_text='Suma de cobros a cuenta aplicados. Saldo = monto − monto_cobrado.',
                max_digits=14,
            ),
        ),
        migrations.RunPython(backfill_monto_cobrado, migrations.RunPython.noop),
    ]
