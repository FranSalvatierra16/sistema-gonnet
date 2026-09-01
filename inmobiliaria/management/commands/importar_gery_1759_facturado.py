"""Importa Excel de Gery 1759 (facturado o en negro) al libro."""
from django.core.management.base import BaseCommand

from inmobiliaria.gery_1759_facturado_import import importar_gery_1759_excel


class Command(BaseCommand):
    help = 'Importa Excel de Gery 1759 piso 12 como facturado o en negro.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clasificacion',
            choices=('facturado', 'negro'),
            default='facturado',
        )
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true')
        parser.add_argument(
            '--replace',
            action='store_true',
            help='Borra filas previas de esa clasificación y carga el Excel de cero.',
        )
        parser.add_argument('--json', default=None)

    def handle(self, *args, **options):
        result = importar_gery_1759_excel(
            clasificacion=options['clasificacion'],
            dry_run=options['dry_run'],
            force=options['force'],
            replace=options['replace'],
            json_path=options['json'],
        )
        if result['ok']:
            self.stdout.write(self.style.SUCCESS(result['mensaje']))
        else:
            self.stderr.write(self.style.ERROR(result['mensaje']))
