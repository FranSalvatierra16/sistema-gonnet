# Add es_manual field to Disponibilidad

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0048_caja_id_propiedad_titulo_alter_caja_numero'),
    ]

    operations = [
        migrations.AddField(
            model_name='disponibilidad',
            name='es_manual',
            field=models.BooleanField(default=True, help_text='True si fue creada manualmente, False si fue generada automáticamente'),
        ),
    ]
