from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0212_operacion_sin_fichaje'),
    ]

    operations = [
        migrations.AddField(
            model_name='comisionvendedor',
            name='eliminada_manual',
            field=models.BooleanField(
                default=False,
                help_text='Eliminada desde el detalle de comisiones: queda cancelada y no se vuelve a generar.',
                verbose_name='Eliminada a mano',
            ),
        ),
    ]
