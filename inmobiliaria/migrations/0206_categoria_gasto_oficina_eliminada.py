from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0205_reporte_deptos_oficina_preferencia'),
    ]

    operations = [
        migrations.AddField(
            model_name='categoriagastooficina',
            name='eliminada',
            field=models.BooleanField(
                default=False,
                help_text='Borrada por el usuario; no se vuelve a crear al sincronizar el seed.',
            ),
        ),
    ]
