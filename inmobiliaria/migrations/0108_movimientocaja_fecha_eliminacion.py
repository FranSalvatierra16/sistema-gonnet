# Generated manually for soft-delete de movimientos de caja

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('inmobiliaria', '0107_vendedor_comision_por_dia_etiqueta'),
    ]

    operations = [
        migrations.AddField(
            model_name='movimientocaja',
            name='fecha_eliminacion',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text='Si está informado, el movimiento fue anulado y no suma en el saldo de la caja.',
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='movimientocaja',
            name='eliminado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='movimientos_caja_eliminados',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
