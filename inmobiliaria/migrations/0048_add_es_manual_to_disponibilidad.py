# Add es_manual field to Disponibilidad

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0047_add_es_principal_to_historial'),
    ]

    operations = [
        migrations.AddField(
            model_name='disponibilidad',
            name='es_manual',
            field=models.BooleanField(default=True, help_text='True si fue creada manualmente, False si fue generada automáticamente'),
        ),
    ]
