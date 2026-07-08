from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0155_historial_inquilino'),
    ]

    operations = [
        migrations.AddField(
            model_name='reserva',
            name='ocultar_en_historial_inquilino',
            field=models.BooleanField(
                default=False,
                help_text='Si está marcada, no aparece en el historial del inquilino (p. ej. duplicados borrados a propósito).',
                verbose_name='Ocultar en historial del inquilino',
            ),
        ),
    ]
