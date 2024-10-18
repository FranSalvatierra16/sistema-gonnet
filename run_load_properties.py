import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sistema_gonnet.settings")
django.setup()

from inmobiliaria.management.commands.load_properties import Command

if __name__ == "__main__":
    command = Command()
    command.handle()
