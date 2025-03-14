# Generated by Django 4.2.7 on 2024-12-16 14:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0015_alter_pago_options'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='pago',
            options={'ordering': ['-fecha']},
        ),
        migrations.RemoveField(
            model_name='reserva',
            name='deposito',
        ),
        migrations.AddField(
            model_name='reserva',
            name='deposito_garantia',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
    ]
