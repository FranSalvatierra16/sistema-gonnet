import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0123_cartera_propiedad_usuario'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='carterapropiedadusuario',
            name='inquilino',
        ),
        migrations.AddField(
            model_name='carterapropiedadusuario',
            name='propietario',
            field=models.ForeignKey(
                blank=True,
                help_text='Propietario usado al agregar la propiedad (referencia).',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='carteras_por_propietario',
                to='inmobiliaria.propietario',
            ),
        ),
    ]
