from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0178_portal_web_publicar_consulta'),
    ]

    operations = [
        migrations.AddField(
            model_name='costoscompralibropropiedad',
            name='escribania',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Escribanía donde se realizó la escritura.',
                max_length=255,
                verbose_name='Escribanía',
            ),
        ),
        migrations.AddField(
            model_name='costoscompralibropropiedad',
            name='observaciones',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Notas libres del depto (visible en el libro de oficina).',
                verbose_name='Observaciones del departamento',
            ),
        ),
    ]
