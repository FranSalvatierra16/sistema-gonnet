# Generated by Django 4.2.7 on 2024-11-07 17:28

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inmobiliaria', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='propiedad',
            name='id',
            field=models.CharField(max_length=2000, primary_key=True, serialize=False, unique=True),
        ),
    ]
