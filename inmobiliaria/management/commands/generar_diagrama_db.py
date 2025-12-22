"""
Comando de Django para generar un diagrama HTML de la estructura de la base de datos
"""
from django.core.management.base import BaseCommand
from django.apps import apps
from django.db import models
from django.conf import settings
import os


class Command(BaseCommand):
    help = 'Genera un archivo HTML con un diagrama visual de la estructura de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--app',
            type=str,
            help='Generar diagrama solo para una app específica (ej: inmobiliaria)',
        )
        parser.add_argument(
            '--output',
            type=str,
            default='diagrama_db.html',
            help='Nombre del archivo de salida (default: diagrama_db.html)',
        )
        parser.add_argument(
            '--pdf',
            action='store_true',
            help='Generar también una versión PDF del diagrama',
        )

    def handle(self, *args, **options):
        app_name = options.get('app')
        output_file = options.get('output')
        
        self.stdout.write(self.style.SUCCESS('Generando diagrama de la base de datos...'))
        
        # Obtener todas las apps instaladas
        if app_name:
            try:
                apps_to_check = [apps.get_app_config(app_name)]
            except LookupError:
                self.stdout.write(self.style.ERROR(f'App "{app_name}" no encontrada'))
                return
        else:
            apps_to_check = apps.get_app_configs()
        
        # Generar HTML
        html_content = self.generar_html(apps_to_check)
        
        # Guardar archivo HTML
        output_path = os.path.join(settings.BASE_DIR, output_file)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        self.stdout.write(self.style.SUCCESS(f'\n✅ Diagrama HTML generado exitosamente: {output_path}'))
        self.stdout.write(self.style.SUCCESS(f'   Abre el archivo en tu navegador para ver la estructura completa'))
        
        # Generar PDF si se solicita
        if options.get('pdf'):
            try:
                from xhtml2pdf import pisa
                import io
                
                pdf_output = output_file.replace('.html', '.pdf')
                pdf_path = os.path.join(settings.BASE_DIR, pdf_output)
                
                self.stdout.write(self.style.SUCCESS('Generando versión PDF...'))
                
                # Generar PDF
                result = io.BytesIO()
                pdf = pisa.pisaDocument(
                    io.BytesIO(html_content.encode('UTF-8')),
                    result,
                    encoding='UTF-8'
                )
                
                if pdf.err:
                    self.stdout.write(self.style.ERROR(f'Error al generar PDF: {pdf.err}'))
                else:
                    with open(pdf_path, 'wb') as f:
                        f.write(result.getvalue())
                    self.stdout.write(self.style.SUCCESS(f'✅ PDF generado exitosamente: {pdf_path}'))
                
                result.close()
            except ImportError:
                self.stdout.write(self.style.WARNING('xhtml2pdf no está instalado. Instala con: pip install xhtml2pdf'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error al generar PDF: {str(e)}'))
        
        # Mostrar instrucciones de compartir
        self.mostrar_instrucciones_compartir(output_path)

    def mostrar_instrucciones_compartir(self, file_path):
        """Muestra instrucciones de cómo compartir el archivo"""
        self.stdout.write(self.style.SUCCESS('\n' + '='*70))
        self.stdout.write(self.style.SUCCESS('📤 FORMAS DE COMPARTIR EL ARCHIVO:'))
        self.stdout.write(self.style.SUCCESS('='*70))
        self.stdout.write('\n1. 📧 Por Email:')
        self.stdout.write('   - Adjunta el archivo HTML al email')
        self.stdout.write('   - La persona puede abrirlo directamente con su navegador')
        self.stdout.write('\n2. ☁️ Google Drive / Dropbox:')
        self.stdout.write('   - Sube el archivo a la nube')
        self.stdout.write('   - Comparte el enlace')
        self.stdout.write('   - La persona puede descargarlo y abrirlo')
        self.stdout.write('\n3. 💬 WhatsApp / Telegram:')
        self.stdout.write('   - Envía el archivo como documento')
        self.stdout.write('   - La persona puede abrirlo desde su teléfono o computadora')
        self.stdout.write('\n4. 🖥️ Servidor Web (si tienes uno):')
        self.stdout.write('   - Sube el archivo a tu servidor')
        self.stdout.write('   - Comparte la URL')
        self.stdout.write('\n5. 📄 Versión PDF (recomendado para imprimir):')
        self.stdout.write('   - Ejecuta: python3 manage.py generar_diagrama_db --pdf')
        self.stdout.write('   - Se generará un archivo PDF que es más fácil de compartir')
        self.stdout.write('\n' + '='*70 + '\n')

    def generar_html(self, apps_to_check):
        """Genera el contenido HTML con la estructura de las tablas"""
        
        modelos_info = []
        total_modelos = 0
        
        for app_config in apps_to_check:
            modelos = app_config.get_models()
            
            if not modelos:
                continue
            
            for model in sorted(modelos, key=lambda x: x.__name__):
                info = self.obtener_info_modelo(model)
                modelos_info.append(info)
                total_modelos += 1
        
        # Generar HTML
        html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Estructura de Base de Datos</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            min-height: 100vh;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
        }}
        
        .header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        
        .controls {{
            padding: 20px;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }}
        
        .controls input {{
            padding: 10px 15px;
            border: 2px solid #dee2e6;
            border-radius: 8px;
            font-size: 14px;
            flex: 1;
            min-width: 200px;
        }}
        
        .controls button {{
            padding: 10px 20px;
            background: #667eea;
            color: white;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 14px;
            transition: background 0.3s;
        }}
        
        .controls button:hover {{
            background: #5568d3;
        }}
        
        .stats {{
            padding: 15px 20px;
            background: #e9ecef;
            display: flex;
            gap: 30px;
            flex-wrap: wrap;
        }}
        
        .stat-item {{
            display: flex;
            flex-direction: column;
        }}
        
        .stat-label {{
            font-size: 12px;
            color: #6c757d;
            text-transform: uppercase;
        }}
        
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #667eea;
        }}
        
        .content {{
            padding: 30px;
        }}
        
        .modelo-card {{
            background: white;
            border: 2px solid #dee2e6;
            border-radius: 12px;
            margin-bottom: 30px;
            overflow: hidden;
            transition: transform 0.3s, box-shadow 0.3s;
        }}
        
        .modelo-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(0,0,0,0.15);
        }}
        
        .modelo-header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .modelo-header h2 {{
            font-size: 1.5em;
            margin: 0;
        }}
        
        .modelo-header .toggle {{
            font-size: 1.2em;
            transition: transform 0.3s;
        }}
        
        .modelo-header.collapsed .toggle {{
            transform: rotate(-90deg);
        }}
        
        .modelo-body {{
            padding: 25px;
            display: block;
        }}
        
        .modelo-body.hidden {{
            display: none;
        }}
        
        .info-section {{
            margin-bottom: 25px;
        }}
        
        .info-section h3 {{
            color: #667eea;
            margin-bottom: 15px;
            font-size: 1.2em;
            border-bottom: 2px solid #dee2e6;
            padding-bottom: 10px;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
            margin-bottom: 15px;
        }}
        
        .info-item {{
            background: #f8f9fa;
            padding: 12px;
            border-radius: 8px;
            border-left: 4px solid #667eea;
        }}
        
        .info-item strong {{
            color: #495057;
            display: block;
            margin-bottom: 5px;
        }}
        
        .info-item span {{
            color: #6c757d;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        
        table th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}
        
        table td {{
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
        }}
        
        table tr:hover {{
            background: #f8f9fa;
        }}
        
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            font-weight: 600;
            margin: 2px;
        }}
        
        .badge-primary {{
            background: #667eea;
            color: white;
        }}
        
        .badge-success {{
            background: #28a745;
            color: white;
        }}
        
        .badge-warning {{
            background: #ffc107;
            color: #212529;
        }}
        
        .badge-danger {{
            background: #dc3545;
            color: white;
        }}
        
        .badge-info {{
            background: #17a2b8;
            color: white;
        }}
        
        .relacion {{
            background: #e7f3ff;
            padding: 10px;
            border-radius: 8px;
            margin: 5px 0;
            border-left: 4px solid #17a2b8;
        }}
        
        .relacion strong {{
            color: #17a2b8;
        }}
        
        .no-results {{
            text-align: center;
            padding: 60px;
            color: #6c757d;
        }}
        
        .no-results h3 {{
            font-size: 1.5em;
            margin-bottom: 10px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Estructura de Base de Datos</h1>
            <p>Diagrama completo de tablas y relaciones</p>
            <div style="margin-top: 15px; font-size: 0.9em; opacity: 0.8;">
                <strong>💡 Para compartir:</strong> Este archivo es independiente. 
                Puedes enviarlo por email, WhatsApp, Google Drive, etc. 
                La otra persona solo necesita abrirlo con cualquier navegador.
            </div>
        </div>
        
        <div class="controls">
            <input type="text" id="searchInput" placeholder="🔍 Buscar tabla, campo o relación...">
            <button onclick="expandAll()">Expandir Todo</button>
            <button onclick="collapseAll()">Colapsar Todo</button>
            <button onclick="window.print()">🖨️ Imprimir</button>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <span class="stat-label">Total de Tablas</span>
                <span class="stat-value">{total_modelos}</span>
            </div>
            <div class="stat-item">
                <span class="stat-label">Apps</span>
                <span class="stat-value">{len(apps_to_check)}</span>
            </div>
        </div>
        
        <div class="content" id="content">
"""
        
        # Agregar cada modelo
        for info in modelos_info:
            html += self.generar_card_modelo(info)
        
        html += """
        </div>
    </div>
    
    <script>
        // Búsqueda
        document.getElementById('searchInput').addEventListener('input', function(e) {
            const searchTerm = e.target.value.toLowerCase();
            const cards = document.querySelectorAll('.modelo-card');
            
            cards.forEach(card => {
                const text = card.textContent.toLowerCase();
                if (text.includes(searchTerm)) {
                    card.style.display = 'block';
                } else {
                    card.style.display = 'none';
                }
            });
        });
        
        // Toggle cards
        document.querySelectorAll('.modelo-header').forEach(header => {
            header.addEventListener('click', function() {
                const body = this.nextElementSibling;
                this.classList.toggle('collapsed');
                body.classList.toggle('hidden');
            });
        });
        
        function expandAll() {
            document.querySelectorAll('.modelo-body').forEach(body => {
                body.classList.remove('hidden');
            });
            document.querySelectorAll('.modelo-header').forEach(header => {
                header.classList.remove('collapsed');
            });
        }
        
        function collapseAll() {
            document.querySelectorAll('.modelo-body').forEach(body => {
                body.classList.add('hidden');
            });
            document.querySelectorAll('.modelo-header').forEach(header => {
                header.classList.add('collapsed');
            });
        }
    </script>
</body>
</html>
"""
        
        return html

    def obtener_info_modelo(self, model):
        """Obtiene toda la información de un modelo"""
        meta = model._meta
        
        campos = []
        for field in meta.get_fields():
            if isinstance(field, (models.ManyToOneRel, models.OneToOneRel)):
                continue
            if isinstance(field, models.ManyToManyField):
                continue
            
            campo_info = {
                'nombre': field.name,
                'tipo': self.get_tipo_campo(field),
                'null': 'Sí' if hasattr(field, 'null') and field.null else 'No',
                'default': self.get_default(field),
                'opciones': self.get_opciones(field)
            }
            campos.append(campo_info)
        
        relaciones_fk = []
        relaciones_m2m = []
        relaciones_o2o = []
        
        for field in meta.get_fields():
            if isinstance(field, models.ForeignKey):
                on_delete = field.remote_field.on_delete.__name__ if hasattr(field.remote_field, 'on_delete') else 'CASCADE'
                related = field.related_model.__name__ if field.related_model else 'Unknown'
                relaciones_fk.append({
                    'campo': field.name,
                    'relacionado': related,
                    'on_delete': on_delete
                })
            elif isinstance(field, models.ManyToManyField):
                related = field.related_model.__name__ if field.related_model else 'Unknown'
                relaciones_m2m.append({
                    'campo': field.name,
                    'relacionado': related
                })
            elif isinstance(field, models.OneToOneField):
                related = field.related_model.__name__ if field.related_model else 'Unknown'
                relaciones_o2o.append({
                    'campo': field.name,
                    'relacionado': related
                })
        
        constraints = []
        if hasattr(meta, 'constraints') and meta.constraints:
            for constraint in meta.constraints:
                if isinstance(constraint, models.UniqueConstraint):
                    fields = ', '.join(constraint.fields)
                    constraints.append({
                        'tipo': 'UNIQUE',
                        'campos': fields,
                        'nombre': constraint.name
                    })
        
        return {
            'nombre': model.__name__,
            'tabla': meta.db_table,
            'app': meta.app_label,
            'verbose_name': meta.verbose_name,
            'verbose_name_plural': meta.verbose_name_plural,
            'campos': campos,
            'fk': relaciones_fk,
            'm2m': relaciones_m2m,
            'o2o': relaciones_o2o,
            'constraints': constraints
        }

    def generar_card_modelo(self, info):
        """Genera el HTML para una card de modelo"""
        html = f"""
            <div class="modelo-card">
                <div class="modelo-header collapsed">
                    <h2>📋 {info['nombre']}</h2>
                    <span class="toggle">▼</span>
                </div>
                <div class="modelo-body hidden">
                    <div class="info-section">
                        <h3>📊 Información General</h3>
                        <div class="info-grid">
                            <div class="info-item">
                                <strong>Tabla en BD:</strong>
                                <span>{info['tabla']}</span>
                            </div>
                            <div class="info-item">
                                <strong>App:</strong>
                                <span>{info['app']}</span>
                            </div>
                            <div class="info-item">
                                <strong>Nombre:</strong>
                                <span>{info['verbose_name']}</span>
                            </div>
                            <div class="info-item">
                                <strong>Plural:</strong>
                                <span>{info['verbose_name_plural']}</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="info-section">
                        <h3>📝 Campos ({len(info['campos'])})</h3>
                        <table>
                            <thead>
                                <tr>
                                    <th>Nombre</th>
                                    <th>Tipo</th>
                                    <th>NULL</th>
                                    <th>Default</th>
                                    <th>Opciones</th>
                                </tr>
                            </thead>
                            <tbody>
"""
        
        for campo in info['campos']:
            opciones_html = ' '.join([f'<span class="badge badge-{self.get_badge_class(op)}">{op}</span>' 
                                     for op in campo['opciones']]) if campo['opciones'] else '-'
            
            html += f"""
                                <tr>
                                    <td><strong>{campo['nombre']}</strong></td>
                                    <td>{campo['tipo']}</td>
                                    <td>{campo['null']}</td>
                                    <td>{campo['default']}</td>
                                    <td>{opciones_html}</td>
                                </tr>
"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
"""
        
        if info['fk']:
            html += """
                    <div class="info-section">
                        <h3>🔗 Foreign Keys</h3>
"""
            for fk in info['fk']:
                html += f"""
                        <div class="relacion">
                            <strong>{fk['campo']}</strong> → <strong>{fk['relacionado']}</strong> 
                            <span class="badge badge-info">on_delete={fk['on_delete']}</span>
                        </div>
"""
            html += """
                    </div>
"""
        
        if info['m2m']:
            html += """
                    <div class="info-section">
                        <h3>🔗 Many to Many</h3>
"""
            for m2m in info['m2m']:
                html += f"""
                        <div class="relacion">
                            <strong>{m2m['campo']}</strong> ↔ <strong>{m2m['relacionado']}</strong>
                        </div>
"""
            html += """
                    </div>
"""
        
        if info['o2o']:
            html += """
                    <div class="info-section">
                        <h3>🔗 One to One</h3>
"""
            for o2o in info['o2o']:
                html += f"""
                        <div class="relacion">
                            <strong>{o2o['campo']}</strong> ⇄ <strong>{o2o['relacionado']}</strong>
                        </div>
"""
            html += """
                    </div>
"""
        
        if info['constraints']:
            html += """
                    <div class="info-section">
                        <h3>🔒 Constraints</h3>
"""
            for constraint in info['constraints']:
                html += f"""
                        <div class="relacion">
                            <strong>{constraint['tipo']}</strong> ({constraint['campos']}) - {constraint['nombre']}
                        </div>
"""
            html += """
                    </div>
"""
        
        html += """
                </div>
            </div>
"""
        
        return html

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

    def get_default(self, field):
        """Obtiene el valor por defecto del campo"""
        if hasattr(field, 'default'):
            if field.default == models.NOT_PROVIDED:
                return '-'
            elif callable(field.default):
                return f'{field.default.__name__}()'
            else:
                return str(field.default)
        return '-'

    def get_opciones(self, field):
        """Obtiene las opciones del campo"""
        opciones = []
        if hasattr(field, 'blank') and field.blank:
            opciones.append('blank')
        if hasattr(field, 'unique') and field.unique:
            opciones.append('unique')
        if hasattr(field, 'primary_key') and field.primary_key:
            opciones.append('PK')
        if hasattr(field, 'max_length') and field.max_length:
            opciones.append(f'max={field.max_length}')
        return opciones

    def get_badge_class(self, opcion):
        """Determina la clase CSS del badge según la opción"""
        if 'PK' in opcion:
            return 'danger'
        elif 'unique' in opcion:
            return 'warning'
        elif 'blank' in opcion:
            return 'info'
        else:
            return 'primary'

