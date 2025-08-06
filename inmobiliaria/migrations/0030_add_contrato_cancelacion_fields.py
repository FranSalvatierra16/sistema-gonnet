from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('inmobiliaria', '0029_alter_caja_table'),
    ]

    operations = [
        migrations.AddField(
            model_name='contratoalquiler',
            name='fecha_cancelacion',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='contratoalquiler',
            name='motivo_cancelacion',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='contratoalquiler',
            name='estado',
            field=models.CharField(
                choices=[
                    ('reservado', 'Reservado'),
                    ('activo', 'Activo'),
                    ('finalizado', 'Finalizado'),
                    ('rescindido', 'Rescindido')
                ],
                default='reservado',
                max_length=20
            ),
        ),
    ] 