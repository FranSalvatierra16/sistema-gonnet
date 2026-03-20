from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0087_quitar_locatarios_de_garantes'),
    ]

    operations = [
        migrations.AddField(
            model_name='liquidacionpropietario',
            name='operaciones_incluidas',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de {"tipo": "reserva"|"contrato", "id": <pk>} para excluir del listado de pendientes',
                verbose_name='Operaciones incluidas',
            ),
        ),
    ]
