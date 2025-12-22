"""
Comando de Django para mostrar la estructura de todos los modelos
Basado en los modelos de Django, no requiere conexión a la base de datos
"""
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models


class Command(BaseCommand):
    help = 'Muestra la estructura completa de todos los modelos de Django'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            help='Mostrar solo los modelos de una app específica (ej: inmobiliaria)',
        )
        parser.add_argument(
            '--modelo',
            type=str,
            help='Mostrar solo un modelo específico',
        )

    def handle(self, *args, **options):
        app_name = options.get('app')
        modelo_name = options.get('modelo')
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*100))
        self.stdout.write(self.style.SUCCESS('ESTRUCTURA DE MODELOS DE DJANGO'))
        self.stdout.write(self.style.SUCCESS('='*100 + '\n'))
        
        # Obtener todas las apps instaladas
        if app_name:
            try:
                apps_to_check = [apps.get_app_config(app_name)]
            except LookupError:
                self.stdout.write(self.style.ERROR(f'App "{app_name}" no encontrada'))
                return
        else:
            apps_to_check = apps.get_app_configs()
        
        total_modelos = 0
        
        # Mostrar información de cada modelo
        for app_config in apps_to_check:
            modelos = app_config.get_models()
            
            if not modelos:
                continue
            
            self.stdout.write(self.style.WARNING(f'\n📦 APP: {app_config.verbose_name} ({app_config.name})'))
            self.stdout.write(self.style.WARNING('='*100))
            
            for model in sorted(modelos, key=lambda x: x.__name__):
                if modelo_name and modelo_name.lower() not in model.__name__.lower():
                    continue
                
                self.mostrar_modelo(model)
                total_modelos += 1
                self.stdout.write('')
        
        self.stdout.write(self.style.SUCCESS('='*100))
        self.stdout.write(self.style.SUCCESS(f'Total de modelos mostrados: {total_modelos}'))
        self.stdout.write(self.style.SUCCESS('='*100 + '\n'))

    def mostrar_modelo(self, model):
        """Muestra la información detallada de un modelo"""
        meta = model._meta
        
        # Encabezado
        self.stdout.write(self.style.WARNING(f'\n📋 MODELO: {model.__name__}'))
        self.stdout.write('-' * 100)
        
        # Información básica
        self.stdout.write(f'🔹 Tabla en BD: {meta.db_table}')
        self.stdout.write(f'🔹 App: {meta.app_label}')
        self.stdout.write(f'🔹 Verbose Name: {meta.verbose_name}')
        self.stdout.write(f'🔹 Verbose Name Plural: {meta.verbose_name_plural}')
        
        # Campos (solo campos directos, no relaciones inversas)
        self.stdout.write('\n📊 CAMPOS:')
        self.stdout.write('-' * 100)
        self.stdout.write(f"{'Nombre':<30} {'Tipo':<25} {'NULL':<8} {'Default':<15} {'Opciones':<20}")
        self.stdout.write('-' * 100)
        
        # Obtener solo campos directos (no relaciones inversas)
        for field in meta.get_fields():
            # Saltar relaciones inversas (ManyToOneRel, OneToOneRel)
            if isinstance(field, (models.ManyToOneRel, models.OneToOneRel)):
                continue
            if isinstance(field, models.ManyToManyField):
                continue  # Los M2M se muestran después
            
            nombre = field.name
            tipo = self.get_tipo_campo(field)
            nullable = 'Sí' if hasattr(field, 'null') and field.null else 'No'
            
            # Manejar default de forma segura
            if hasattr(field, 'default'):
                if field.default == models.NOT_PROVIDED:
                    default = '-'
                elif callable(field.default):
                    default = f'{field.default.__name__}()'
                else:
                    default = str(field.default)
            else:
                default = '-'
            
            if default == '<django.db.models.query_utils.DeferredAttribute object>':
                default = 'Auto'
            
            # Información adicional
            opciones = []
            if hasattr(field, 'blank') and field.blank:
                opciones.append('blank')
            if hasattr(field, 'unique') and field.unique:
                opciones.append('unique')
            if hasattr(field, 'primary_key') and field.primary_key:
                opciones.append('PK')
            if hasattr(field, 'max_length') and field.max_length:
                opciones.append(f'max={field.max_length}')
            
            opciones_str = ', '.join(opciones) if opciones else '-'
            
            self.stdout.write(f"{nombre:<30} {tipo:<25} {nullable:<8} {default:<15} {opciones_str:<20}")
        
        # Relaciones ForeignKey
        fk_fields = [f for f in meta.get_fields() if isinstance(f, models.ForeignKey)]
        if fk_fields:
            self.stdout.write('\n🔗 FOREIGN KEYS:')
            self.stdout.write('-' * 100)
            for field in fk_fields:
                on_delete = field.remote_field.on_delete.__name__ if hasattr(field.remote_field, 'on_delete') else 'CASCADE'
                related_model = field.related_model.__name__ if field.related_model else 'Unknown'
                self.stdout.write(f"  • {field.name} → {related_model} (on_delete={on_delete})")
        
        # Relaciones ManyToMany
        m2m_fields = [f for f in meta.get_fields() if isinstance(f, models.ManyToManyField)]
        if m2m_fields:
            self.stdout.write('\n🔗 MANY TO MANY:')
            self.stdout.write('-' * 100)
            for field in m2m_fields:
                related_model = field.related_model.__name__ if field.related_model else 'Unknown'
                self.stdout.write(f"  • {field.name} ↔ {related_model}")
        
        # Relaciones OneToOne
        o2o_fields = [f for f in meta.get_fields() if isinstance(f, models.OneToOneField)]
        if o2o_fields:
            self.stdout.write('\n🔗 ONE TO ONE:')
            self.stdout.write('-' * 100)
            for field in o2o_fields:
                related_model = field.related_model.__name__ if field.related_model else 'Unknown'
                self.stdout.write(f"  • {field.name} ⇄ {related_model}")
        
        # Constraints
        if hasattr(meta, 'constraints') and meta.constraints:
            self.stdout.write('\n🔒 CONSTRAINTS:')
            self.stdout.write('-' * 100)
            for constraint in meta.constraints:
                if isinstance(constraint, models.UniqueConstraint):
                    fields = ', '.join(constraint.fields)
                    name = constraint.name
                    condition = f" WHERE {constraint.condition}" if hasattr(constraint, 'condition') and constraint.condition else ""
                    self.stdout.write(f"  • UNIQUE ({fields}){condition} - {name}")
                elif isinstance(constraint, models.CheckConstraint):
                    self.stdout.write(f"  • CHECK: {constraint.check} - {constraint.name}")
        
        # Índices
        if hasattr(meta, 'indexes') and meta.indexes:
            self.stdout.write('\n🔑 ÍNDICES:')
            self.stdout.write('-' * 100)
            for index in meta.indexes:
                fields = ', '.join(index.fields)
                self.stdout.write(f"  • {index.name}: ({fields})")

    def get_tipo_campo(self, field):
        """Obtiene una representación legible del tipo de campo"""
        tipo_base = type(field).__name__
        
        if isinstance(field, models.CharField):
            return f"CharField({field.max_length})"
        elif isinstance(field, models.TextField):
            return "TextField"
        elif isinstance(field, models.IntegerField):
            return "IntegerField"
        elif isinstance(field, models.BigIntegerField):
            return "BigIntegerField"
        elif isinstance(field, models.PositiveIntegerField):
            return "PositiveIntegerField"
        elif isinstance(field, models.DecimalField):
            return f"DecimalField({field.max_digits},{field.decimal_places})"
        elif isinstance(field, models.FloatField):
            return "FloatField"
        elif isinstance(field, models.BooleanField):
            return "BooleanField"
        elif isinstance(field, models.DateField):
            return "DateField"
        elif isinstance(field, models.DateTimeField):
            return "DateTimeField"
        elif isinstance(field, models.TimeField):
            return "TimeField"
        elif isinstance(field, models.EmailField):
            return f"EmailField({field.max_length})"
        elif isinstance(field, models.URLField):
            return f"URLField({field.max_length})"
        elif isinstance(field, models.ForeignKey):
            related = field.related_model.__name__ if field.related_model else 'Unknown'
            return f"ForeignKey({related})"
        elif isinstance(field, models.ManyToManyField):
            related = field.related_model.__name__ if field.related_model else 'Unknown'
            return f"ManyToManyField({related})"
        elif isinstance(field, models.OneToOneField):
            related = field.related_model.__name__ if field.related_model else 'Unknown'
            return f"OneToOneField({related})"
        elif isinstance(field, models.FileField):
            return "FileField"
        elif isinstance(field, models.ImageField):
            return "ImageField"
        else:
            return tipo_base

