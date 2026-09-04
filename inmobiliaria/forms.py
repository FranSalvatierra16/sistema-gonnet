from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import (
    Vendedor, 
    Inquilino, 
    Propietario, 
    Propiedad, 
    Reserva, 
    Disponibilidad, 
    ImagenPropiedad, 
    Precio,
    TipoPrecio,
    TIPOS_INMUEBLES, 
    TIPOS_VISTA, 
    TIPOS_VALORACION, 
    Sucursal, 
    VentaPropiedad, 
    MovimientoCaja, 
    Concepto, 
    BancoTarjeta,
    Registro
)
from datetime import datetime
from django.forms import modelformset_factory
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models
import os
from django.utils import timezone
# Formulario de creación de Vendedor
class VendedorUserCreationForm(forms.ModelForm):
    username = forms.CharField(max_length=150, help_text='Requerido. 150 caracteres o menos.')
    password1 = forms.CharField(widget=forms.PasswordInput, help_text='Requerido.')
    password2 = forms.CharField(widget=forms.PasswordInput, help_text='Ingrese la misma contraseña para verificar.')

    sucursal = forms.ModelChoiceField(
        queryset=Sucursal.objects.all(),
        required=True,
        help_text='Seleccione la sucursal a la que pertenece el vendedor.'
    )

    class Meta:
        model = Vendedor
        fields = [
            'dni', 'username', 'nombre', 'apellido', 'email', 'comision',
            'comision_primer_fichaje', 'comision_segundo_fichaje',
            'comision_primer_fichaje_invierno', 'comision_segundo_fichaje_invierno',
            'comision_primer_fichaje_24_meses', 'comision_segundo_fichaje_24_meses',
            'comision_alquiler_24_meses', 'comision_invierno',
            'comision_alquiler_24_meses_propiedad_oficina', 'comision_invierno_propiedad_oficina',
            'fecha_nacimiento', 'nivel', 'sucursal',
        ]
        widgets = {
            'comision': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'comision_primer_fichaje': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_primer_fichaje_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_primer_fichaje_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_alquiler_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_invierno_propiedad_oficina': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_alquiler_24_meses_propiedad_oficina': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
        }

    def clean_password2(self):
        password1 = self.cleaned_data.get("password1")
        print(password1)
        password2 = self.cleaned_data.get("password2")
        print(password2)
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Las contraseñas no coinciden")
        return password2

    def __init__(self, *args, **kwargs):
        self.puede_editar_nivel = kwargs.pop('puede_editar_nivel', False)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['sucursal'].required = True
        # Solo la sucursal del usuario logueado (Colón / Corrientes no se mezclan).
        if self.user and getattr(self.user, 'sucursal_id', None):
            self.fields['sucursal'].queryset = Sucursal.objects.filter(pk=self.user.sucursal_id)
            self.fields['sucursal'].initial = self.user.sucursal
            self.fields['sucursal'].disabled = True
            self.fields['sucursal'].help_text = (
                'El vendedor queda en la misma sucursal desde la que lo estás creando.'
            )
        if 'nivel' in self.fields and not self.puede_editar_nivel:
            self.fields['nivel'].disabled = True
            self.fields['nivel'].help_text = (
                'Solo un super administrador (nivel 5) puede asignar o cambiar el nivel.'
            )
            self.fields['nivel'].required = False

    def clean_nivel(self):
        if not self.puede_editar_nivel:
            # Alta: nivel por defecto del modelo; no aceptar POST manipulado.
            return self.fields['nivel'].initial or getattr(
                self.Meta.model._meta.get_field('nivel'), 'default', 1
            ) or 1
        return self.cleaned_data.get('nivel')

    def clean_sucursal(self):
        if self.user and getattr(self.user, 'sucursal_id', None):
            return self.user.sucursal
        return self.cleaned_data.get('sucursal')

    def save(self, commit=True):
        vendedor = super().save(commit=False)
        vendedor.set_password(self.cleaned_data["password1"])  # Establecer la contraseña
        if not self.puede_editar_nivel:
            vendedor.nivel = getattr(self.Meta.model._meta.get_field('nivel'), 'default', 1) or 1
        if self.user and getattr(self.user, 'sucursal_id', None):
            vendedor.sucursal = self.user.sucursal
        if commit:
            vendedor.save()
        return vendedor

# Formulario de cambio de Vendedor
class VendedorChangeForm(UserChangeForm):
    class Meta:
        model = Vendedor
        fields = [
            'username', 'dni', 'nombre', 'apellido', 'fecha_nacimiento', 'email', 'comision',
            'comision_primer_fichaje', 'comision_segundo_fichaje',
            'comision_primer_fichaje_invierno', 'comision_segundo_fichaje_invierno',
            'comision_primer_fichaje_24_meses', 'comision_segundo_fichaje_24_meses',
            'comision_alquiler_24_meses', 'comision_invierno',
            'comision_alquiler_24_meses_propiedad_oficina', 'comision_invierno_propiedad_oficina',
            'celular', 'nivel', 'sucursal',
        ]
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
            'sucursal': forms.Select(attrs={'class': 'form-control form-select'}),
            'comision': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'comision_primer_fichaje': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_primer_fichaje_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_primer_fichaje_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_segundo_fichaje_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_alquiler_24_meses': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_invierno': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_invierno_propiedad_oficina': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
            'comision_alquiler_24_meses_propiedad_oficina': forms.NumberInput(
                attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.puede_editar_nivel = kwargs.pop('puede_editar_nivel', False)
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if 'sucursal' in self.fields:
            # No permitir cambiar de Colón a Corrientes (ni al revés).
            if self.user and getattr(self.user, 'sucursal_id', None):
                self.fields['sucursal'].queryset = Sucursal.objects.filter(pk=self.user.sucursal_id)
                self.fields['sucursal'].initial = self.user.sucursal
                self.fields['sucursal'].disabled = True
                self.fields['sucursal'].help_text = (
                    'La sucursal del vendedor no se puede cambiar desde acá.'
                )
            else:
                self.fields['sucursal'].queryset = Sucursal.objects.all().order_by('nombre')
            self.fields['sucursal'].required = True
        if 'nivel' in self.fields and not self.puede_editar_nivel:
            self.fields['nivel'].disabled = True
            self.fields['nivel'].help_text = (
                'Solo un super administrador (nivel 5) puede cambiar el nivel.'
            )
            # Disabled fields are omitted from cleaned_data; keep current value.
            self.fields['nivel'].required = False

    def clean_nivel(self):
        if not self.puede_editar_nivel:
            if self.instance and self.instance.pk:
                return self.instance.nivel
            return 1
        return self.cleaned_data.get('nivel')

    def clean_sucursal(self):
        if self.instance and self.instance.pk and self.instance.sucursal_id:
            return self.instance.sucursal
        if self.user and getattr(self.user, 'sucursal_id', None):
            return self.user.sucursal
        return self.cleaned_data.get('sucursal')

    def save(self, commit=True):
        nivel_previo = None
        if self.instance and self.instance.pk and not self.puede_editar_nivel:
            nivel_previo = self.instance.nivel
        sucursal_previa = None
        if self.instance and self.instance.pk:
            sucursal_previa = self.instance.sucursal
        vendedor = super().save(commit=False)
        if nivel_previo is not None:
            vendedor.nivel = nivel_previo
        if sucursal_previa is not None:
            vendedor.sucursal = sucursal_previa
        elif self.user and getattr(self.user, 'sucursal_id', None):
            vendedor.sucursal = self.user.sucursal
        if commit:
            vendedor.save()
            self.save_m2m()
        return vendedor

# Formulario de Inquilino
class InquilinoForm(forms.ModelForm):
    cuit = forms.CharField(
        max_length=11,
        required=False,
        label='CUIT',
        help_text='CUIT (11 dígitos)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 20123456789'})
    )
    
    class Meta:
        model = Inquilino
        fields = ['nombre', 'apellido', 'email', 'celular', 'tipo_doc', 'dni', 'cuit', 'localidad', 'provincia', 'domicilio', 'observaciones', 'garantia']

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(InquilinoForm, self).__init__(*args, **kwargs)
        # Ocultar tipo_doc del formulario
        if 'tipo_doc' in self.fields:
            self.fields['tipo_doc'].widget = forms.HiddenInput()
            self.fields['tipo_doc'].initial = 'dni'  # Valor por defecto
        
        # Hacer DNI obligatorio
        if 'dni' in self.fields:
            self.fields['dni'].required = True
        
        # Si hay una instancia, cargar el CUIT desde el modelo
        if self.instance and self.instance.pk:
            self.fields['cuit'].initial = self.instance.cuit

    def save(self, commit=True):
        inquilino = super(InquilinoForm, self).save(commit=False)
        if self.user:
            inquilino.sucursal = self.user.sucursal  # Asigna la sucursal del vendedor
        
        # Guardar CUIT si se proporcionó
        if 'cuit' in self.cleaned_data and self.cleaned_data['cuit']:
            inquilino.cuit = self.cleaned_data['cuit']
        
        if commit:
            inquilino.save()
        return inquilino

# Formulario de Propietario
class PropietarioForm(forms.ModelForm):
    sucursales = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Sucursales',
        help_text='Marcá en qué sucursales tiene ficha este propietario.',
    )

    class Meta:
        model = Propietario
        fields = ['nombre', 'apellido', 'fecha_nacimiento', 'email', 'celular', 
                 'tipo_doc', 'dni', 'tipo_ins', 'cuit', 'localidad', 'provincia', 
                 'domicilio', 'observaciones',
                 'cuenta_banco', 'cuenta_titular', 'cuenta_cbu_alias', 'cuenta_numero']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date'}),
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            'cuenta_banco': forms.TextInput(attrs={
                'placeholder': 'Ej: Banco Provincia, Galicia, Mercado Pago',
            }),
            'cuenta_titular': forms.TextInput(attrs={
                'placeholder': 'Titular de la cuenta',
            }),
            'cuenta_cbu_alias': forms.TextInput(attrs={
                'placeholder': 'CBU, CVU o alias',
            }),
            'cuenta_numero': forms.TextInput(attrs={
                'placeholder': 'Opcional — número de cuenta',
            }),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(PropietarioForm, self).__init__(*args, **kwargs)

        from inmobiliaria.propietario_sucursales import (
            get_sucursales_colon_corrientes,
            puede_gestionar_sucursales_propietario,
            propietario_sucursales_vinculadas,
        )

        self._gestiona_sucursales = bool(
            self.user and puede_gestionar_sucursales_propietario(self.user)
        )
        if self._gestiona_sucursales:
            sucursales_qs = get_sucursales_colon_corrientes()
            self.fields['sucursales'].choices = [(str(s.id), s.nombre) for s in sucursales_qs]
            if self.instance and self.instance.pk:
                vinculadas = propietario_sucursales_vinculadas(self.instance)
                self.fields['sucursales'].initial = [str(sid) for sid in vinculadas]
            elif self.user and getattr(self.user, 'sucursal_id', None):
                self.fields['sucursales'].initial = [str(self.user.sucursal_id)]
            self.fields['sucursales'].required = True
        else:
            del self.fields['sucursales']
        
        # Marcar campos requeridos
        self.fields['nombre'].required = True
        self.fields['apellido'].required = True
        self.fields['dni'].required = False  # DNI ahora es opcional
        self.fields['cuit'].required = False
        for _fn in ('cuenta_banco', 'cuenta_titular', 'cuenta_cbu_alias', 'cuenta_numero'):
            self.fields[_fn].required = False
        self.fields['cuenta_banco'].help_text = 'Nombre del banco o billetera (opcional)'
        self.fields['cuenta_titular'].help_text = 'Titular según el banco (opcional)'
        self.fields['cuenta_cbu_alias'].help_text = 'CBU, CVU o alias para transferencias (opcional)'
        self.fields['cuenta_numero'].help_text = 'Número de cuenta solo referencia (opcional)'
        
        # Agregar clases de Bootstrap
        for field in self.fields:
            self.fields[field].widget.attrs.update({
                'class': 'form-control'
            })
        if 'sucursales' in self.fields:
            self.fields['sucursales'].widget.attrs.pop('class', None)

    def clean_sucursales(self):
        if 'sucursales' not in self.fields:
            return []
        sucursales = self.cleaned_data.get('sucursales') or []
        if not sucursales:
            raise forms.ValidationError('Seleccioná al menos una sucursal.')
        if self.instance and self.instance.pk and self.instance.sucursal_id:
            if str(self.instance.sucursal_id) not in sucursales:
                nombre = getattr(self.instance.sucursal, 'nombre', 'esta sucursal')
                raise forms.ValidationError(
                    f'La ficha que estás editando pertenece a {nombre}; esa sucursal debe permanecer marcada.'
                )
        return sucursales

    def save(self, commit=True):
        from inmobiliaria.propietario_sucursales import (
            desvincular_sucursales_no_seleccionadas,
            sincronizar_propietario_en_sucursales,
        )

        propietario = super(PropietarioForm, self).save(commit=False)
        sucursales_sel = self.cleaned_data.get('sucursales') or []
        self._sucursales_no_desvinculadas = []

        if self.user:
            if self._gestiona_sucursales and sucursales_sel:
                sucursal_ids = {int(sid) for sid in sucursales_sel}
                if not propietario.pk or not propietario.sucursal_id:
                    if self.user.sucursal_id in sucursal_ids:
                        propietario.sucursal_id = self.user.sucursal_id
                    else:
                        propietario.sucursal_id = sorted(sucursal_ids)[0]
            elif not propietario.sucursal_id:
                propietario.sucursal = self.user.sucursal

        if commit:
            propietario.save()
            if self._gestiona_sucursales and sucursales_sel:
                sincronizar_propietario_en_sucursales(propietario, sucursales_sel)
                self._sucursales_no_desvinculadas = desvincular_sucursales_no_seleccionadas(
                    propietario, sucursales_sel
                )
        return propietario
class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean_cantidad_personas(self):
        cantidad_personas = self.cleaned_data.get('cantidad_personas')
        if cantidad_personas is not None:
            # Asegurarse de que sea un entero positivo
            if cantidad_personas < 1:
                raise forms.ValidationError("La cantidad de personas debe ser al menos 1.")
            return int(cantidad_personas)
        return cantidad_personas

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = []
            for d in data:
                try:
                    v = single_file_clean(d, initial)
                    if v is not None and getattr(v, 'name', None):
                        result.append(v)
                except forms.ValidationError:
                    raise
                except Exception:
                    pass  # ignorar entradas vacías o inválidas
            return result
        v = single_file_clean(data, initial)
        return [v] if (v is not None and getattr(v, 'name', None)) else []
# Formulario de Propiedad
class PropiedadForm(forms.ModelForm):
    imagenes = MultipleFileField(
        required=False,
        help_text="Seleccione una o más imágenes para la propiedad"
    )
    propietario = forms.ModelChoiceField(
        queryset=Propietario.objects.all(),
        widget=forms.Select(attrs={'class': 'select2-propietario'}),
        required=False
    )
    id = forms.CharField(
        label='Ficha (ID de la propiedad)',
        required=True,
        max_length=Propiedad.ID_MAX_LENGTH,
        strip=True,
        help_text='Número o código único de ficha. En propiedades ya guardadas no se puede modificar desde esta pantalla.',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Ej: 464236',
                'autocomplete': 'off',
            }
        ),
    )
    piso = forms.CharField(
        max_length=10,
        required=False,
        label='Piso',
        help_text='Opcional (lotes, terrenos, cocheras… pueden dejarse vacíos)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: PB, 1, 15 — vacío si no aplica',
        }),
    )
    departamento = forms.CharField(
        max_length=10,
        required=False,
        label='Depto',
        help_text='Opcional si no hay unidad (ej. lote)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ej: 1A, B3 — vacío si no aplica',
        }),
    )
    ambientes = forms.IntegerField(
        required=False,
        label='Ambientes',
        help_text='Opcional (ej. terrenos / lotes)',
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '1',
            'placeholder': '—',
        }),
    )
    
    fichado_por = forms.ModelChoiceField(
        queryset=Vendedor.objects.none(),
        required=False,
        label='Vendedor que tomó la propiedad',
        help_text='Vendedor que cargó o tomó el fichaje de esta propiedad (solo de tu sucursal)',
        widget=forms.Select(attrs={
            'class': 'form-control select2',
            'data-placeholder': 'Buscar por ID o nombre del vendedor...'
        }),
        empty_label="Seleccionar vendedor..."
    )

    numero_por_propietario = forms.IntegerField(
        required=False,
        label='Número de Propiedad',
        help_text='Deje vacío para asignar automáticamente desde el último número del propietario',
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )
    cantidad_personas = forms.IntegerField(
        required=False,
        label='Cantidad de Personas',
        help_text='Cantidad máxima de personas que puede alojar la propiedad',
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 
            'min': '1',
            'step': '1',
            'type': 'number'
        })
    )
    camas = forms.CharField(
        required=False,
        label='Camas',
        help_text='Descripción de las camas (ej: 1 cama matrimonial, 2 camas individuales, etc.)',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 1 cama matrimonial, 2 camas individuales'})
    )
    # Texto libre: número de caja de llaves o texto (ej. depto ocupado en venta → «coordinar»)
    llave = forms.CharField(
        required=False,
        label='Llave (número o texto)',
        max_length=50,
        help_text='Podés poner el número de llave o un texto (ej. «coordinar» si está ocupado y no hay llave física).',
        widget=forms.TextInput(
            attrs={
                'class': 'form-control',
                'placeholder': 'Ej.: 15, coordinar, sin llave…',
                'autocomplete': 'off',
                'inputmode': 'text',
                'maxlength': '50',
            }
        ),
    )

    class Meta:
        model = Propiedad
        fields = [
            'id', 'llave', 'numero_por_propietario', 'direccion', 'titulo', 'ubicacion', 'tipo_inmueble', 'vista', 'piso', 'departamento', 'ambientes', 'valoracion', 'cuenta_bancaria',
            'cantidad_personas', 'camas',
            # 'habilitar_precio_diario', 'precio_diario', 'habilitar_precio_venta', 'precio_venta',
            # 'habilitar_precio_alquiler', 'precio_alquiler',
            'amoblado', 'cochera', 'tv_smart', 'wifi', 'directv_prepago', 'ventilador', 'aire', 'cable',
            'dependencia', 'patio', 'parrilla', 'piscina', 'reciclado', 'a_estrenar', 'terraza', 'balcon', 
            'baulera', 'lavadero', 'seguridad', 'vista_al_Mar', 'vista_panoramica', 'apto_credito', 'descripcion', 'anotaciones',
            'propietario', 'propietario_desde', 'fichado_por', 'tipo_fichaje', 'porcentaje_propietario', 'es_propiedad_oficina',
            'publicar_web', 'destacada_web',
            'latitud', 'longitud',
        ]
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 5, 'class': 'form-control', 'style': 'width: 100%;'}),
            'anotaciones': forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'style': 'width: 100%;', 'placeholder': 'Notas y observaciones sobre la propiedad...'}),
            'valoracion': forms.Select(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'placeholder': 'Ingrese la dirección'}),
            'titulo': forms.TextInput(attrs={'placeholder': 'Título descriptivo (opcional)'}),
            'ubicacion': forms.TextInput(attrs={'placeholder': 'Ingrese la ubicación'}),
            'propietario_desde': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'porcentaje_propietario': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'max': '100',
                'placeholder': '70.00'
            }),
            'tipo_fichaje': forms.Select(attrs={'class': 'form-control'}),
            'publicar_web': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'destacada_web': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'latitud': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0000001', 'placeholder': 'Se completa sola'}),
            'longitud': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0000001', 'placeholder': 'Se completa sola'}),
            # 'precio_venta': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de venta'}),
            # 'precio_alquiler': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio de alquiler'}),
            # 'precio_diario': forms.NumberInput(attrs={'step': 0.01, 'placeholder': 'Precio diario'}),
        }
        
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super(PropiedadForm, self).__init__(*args, **kwargs)
        from inmobiliaria.portal_servicio import usuario_gestiona_portal_web
        if not usuario_gestiona_portal_web(self.user):
            self.fields.pop('publicar_web', None)
            self.fields.pop('destacada_web', None)
        self._pk_inicial = str(self.instance.pk).strip() if self.instance.pk else ''
        self._dir_prev = (
            (getattr(self.instance, 'direccion', None) or '').strip(),
            (getattr(self.instance, 'ubicacion', None) or '').strip(),
        ) if self.instance.pk else None
        if 'id' in self.fields and self._pk_inicial:
            self.fields['id'].initial = self._pk_inicial
            self.fields['id'].disabled = True
            self.fields['id'].help_text = (
                'La ficha no se puede cambiar aquí. Para renombrarla, usar el comando de administración '
                '«renombrar_id_propiedad» (o soporte).'
            )

        # Solo vendedores de la sucursal del usuario (Colón / Corrientes no se mezclan).
        if 'fichado_por' in self.fields:
            qs_vend = Vendedor.objects.none()
            if self.user and getattr(self.user, 'sucursal_id', None):
                qs_vend = Vendedor.objects.filter(
                    sucursal=self.user.sucursal, is_active=True
                ).order_by('apellido', 'nombre')
            # Mantener el fichador actual aunque esté inactivo, si es de la misma sucursal.
            if self.instance.pk and self.instance.fichado_por_id:
                actual = self.instance.fichado_por
                if (
                    actual
                    and self.user
                    and actual.sucursal_id == getattr(self.user, 'sucursal_id', None)
                ):
                    qs_vend = (qs_vend | Vendedor.objects.filter(pk=actual.pk)).distinct()
            self.fields['fichado_por'].queryset = qs_vend

        # Para propiedades existentes, mostrar el vendedor actual seleccionado
        if self.instance.pk and self.instance.fichado_por:
            self.fields['fichado_por'].initial = self.instance.fichado_por
        
        # Para propiedades existentes, mostrar el número de propiedad actual
        if self.instance.pk and self.instance.numero_por_propietario:
            self.fields['numero_por_propietario'].initial = self.instance.numero_por_propietario

        # Refuerzo: llave siempre es texto (nunca input numérico), por si el modelo/cache difiere
        if 'llave' in self.fields:
            self.fields['llave'].widget = forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Ej.: 15, coordinar, sin llave…',
                    'autocomplete': 'off',
                    'inputmode': 'text',
                    'maxlength': '50',
                }
            )
            self.fields['llave'].label = 'Llave (número o texto)'

    def clean_id(self):
        raw = self.cleaned_data.get('id')
        nid = (raw or '').strip() if raw is not None else ''
        if not nid:
            raise ValidationError('La ficha (ID) es obligatoria.')
        if len(nid) > Propiedad.ID_MAX_LENGTH:
            raise ValidationError(
                f'La ficha no puede superar los {Propiedad.ID_MAX_LENGTH} caracteres.'
            )
        qs = Propiedad.all_objects.filter(pk=nid)
        if self._pk_inicial:
            qs = qs.exclude(pk=self._pk_inicial)
        existente = qs.first()
        if existente:
            if getattr(existente, 'eliminada', False):
                raise ValidationError(
                    f'La ficha {nid} está ocupada por una propiedad eliminada. '
                    f'Elegí otro número o recuperá esa ficha desde Propiedades eliminadas.'
                )
            raise ValidationError(
                f'Ya existe la ficha {nid} '
                f'({existente.direccion}'
                f'{(" – " + existente.piso + "°") if existente.piso else ""}'
                f'{(" " + existente.departamento) if existente.departamento else ""}'
                f'). No cambies el número para «reintentar»: esa ficha ya está creada. '
                f'Abrí esa propiedad o elegí una ficha libre si es otra unidad.'
            )
        return nid

    def clean_llave(self):
        raw = self.cleaned_data.get('llave')
        if raw is None:
            return None
        s = str(raw).strip()
        return s if s else None

    def clean_piso(self):
        raw = self.cleaned_data.get('piso')
        if raw is None:
            return ''
        return str(raw).strip()

    def clean_departamento(self):
        raw = self.cleaned_data.get('departamento')
        if raw is None:
            return ''
        return str(raw).strip()

    def clean_ambientes(self):
        v = self.cleaned_data.get('ambientes')
        if v == '' or v is None:
            return None
        return v

    def _update_errors(self, errors):
        """Filtra errores del modelo: solo añade al form campos que existan (evita precio_invierno, etc.)."""
        if hasattr(errors, 'error_dict'):
            new_dict = {}
            for field, messages in errors.error_dict.items():
                if field == NON_FIELD_ERRORS or field in self.fields:
                    new_dict[field] = messages
                else:
                    for msg in messages:
                        self.add_error(None, msg)
            if new_dict:
                super()._update_errors(ValidationError(new_dict))
        else:
            super()._update_errors(errors)

    def clean(self):
        cleaned_data = super().clean()
        
        # Validar campos requeridos (piso, departamento y ambientes son opcionales — ej. lotes en venta)
        campos_requeridos = {
            'id': 'ID de la propiedad',
            'direccion': 'Dirección',
            'ubicacion': 'Ubicación',
            'valoracion': 'Valoración',
            'propietario': 'Propietario',
        }
        
        campos_faltantes = []
        for campo, nombre in campos_requeridos.items():
            valor = cleaned_data.get(campo)
            if not valor:
                campos_faltantes.append(nombre)
                self.add_error(campo, f'{nombre} es requerido')
        
        # Validar que el usuario tenga sucursal asignada
        if self.user and not hasattr(self.user, 'sucursal') or (hasattr(self.user, 'sucursal') and not self.user.sucursal):
            raise ValidationError('El usuario debe tener una sucursal asignada para crear propiedades.')

        # Evitar duplicar la misma unidad con otra ficha (doble click / reintento con otro ID)
        if not self._pk_inicial and self.user and getattr(self.user, 'sucursal_id', None):
            direccion = (cleaned_data.get('direccion') or '').strip()
            piso = (cleaned_data.get('piso') or '').strip()
            depto = (cleaned_data.get('departamento') or '').strip()
            if direccion:
                gemela = (
                    Propiedad.objects.filter(
                        sucursal_id=self.user.sucursal_id,
                        direccion__iexact=direccion,
                        piso__iexact=piso,
                        departamento__iexact=depto,
                    )
                    .exclude(pk=cleaned_data.get('id') or '')
                    .order_by('id')
                    .first()
                )
                if gemela:
                    raise ValidationError(
                        f'Ya existe la ficha {gemela.id} en {gemela.direccion}'
                        f'{(" – " + gemela.piso + "°") if gemela.piso else ""}'
                        f'{(" " + gemela.departamento) if gemela.departamento else ""}. '
                        f'No crees otra con distinto número: abrí esa ficha. '
                        f'Si el sistema dijo que el ID estaba ocupado, es porque el primer intento '
                        f'ya guardó la propiedad (doble clic o demora de red).'
                    )
        
        return cleaned_data
    
    def save(self, commit=True):
        pk_inicial = getattr(self, '_pk_inicial', '') or ''

        propiedad = super(PropiedadForm, self).save(commit=False)
        # Sucursal: solo al crear en BD. No usar "not self.instance.pk": en alta nueva el # de ficha viene del
        # formulario y pk ya está seteado antes del INSERT, entonces la sucursal quedaba vacía.
        if self.user and hasattr(self.user, 'sucursal') and self.user.sucursal:
            if propiedad._state.adding:
                propiedad.sucursal = self.user.sucursal

        fichado_por_seleccionado = self.cleaned_data.get('fichado_por')
        if fichado_por_seleccionado:
            propiedad.fichado_por = fichado_por_seleccionado
            if not pk_inicial or (
                pk_inicial
                and self.instance.fichado_por_id != fichado_por_seleccionado.pk
            ):
                propiedad.fecha_fichado = timezone.now()
        elif not pk_inicial:
            propiedad.fichado_por = None
            propiedad.fecha_fichado = None

        if commit:
            try:
                propiedad.save()
            except Exception as e:
                error_msg = str(e)
                if 'unique constraint' in error_msg.lower() or 'duplicate key' in error_msg.lower():
                    if 'id' in error_msg.lower():
                        raise ValidationError({'id': 'Ya existe una propiedad con este ID. Por favor, elija otro ID.'})
                    elif 'numero_por_propietario' in error_msg.lower():
                        raise ValidationError('El número de propiedad ya existe para este propietario. Se asignará automáticamente un nuevo número.')
                elif 'not null constraint' in error_msg.lower() or 'null value' in error_msg.lower():
                    for campo in ['sucursal', 'propietario', 'direccion', 'ubicacion', 'piso', 'departamento']:
                        if campo in error_msg.lower():
                            raise ValidationError({campo: f'El campo {campo} es requerido y no puede estar vacío.'})
                    raise ValidationError('Faltan campos requeridos. Por favor, complete todos los campos obligatorios.')
                else:
                    raise ValidationError(f'Error al guardar la propiedad: {error_msg}')
            # Guardar imágenes solo si existen
            imagenes = self.cleaned_data.get('imagenes') or []
            if not isinstance(imagenes, (list, tuple)):
                imagenes = [imagenes] if imagenes else []
            imagenes = [f for f in imagenes if f is not None and getattr(f, 'name', None)]
            if imagenes:
                # Obtener el último orden existente
                ultimo_orden = ImagenPropiedad.objects.filter(propiedad=propiedad).aggregate(
                    max_orden=models.Max('orden')
                )['max_orden'] or 0
                
                # Obtener nombres de archivos existentes para evitar duplicados
                imagenes_existentes = ImagenPropiedad.objects.filter(propiedad=propiedad)
                nombres_existentes = {os.path.basename(img.imagen.name) for img in imagenes_existentes}
                
                # Agregar las nuevas imágenes al final, evitando duplicados
                nuevas_agregadas = 0
                for imagen in imagenes:
                    if imagen is None or not getattr(imagen, 'name', None):
                        continue
                    nombre_archivo = os.path.basename(imagen.name)
                    # Si la imagen ya existe, saltarla
                    if nombre_archivo in nombres_existentes:
                        continue
                        
                    nuevas_agregadas += 1
                    ImagenPropiedad.objects.create(
                        propiedad=propiedad,
                        imagen=imagen,
                        orden=ultimo_orden + nuevas_agregadas
                    )
                    nombres_existentes.add(nombre_archivo)
            try:
                from inmobiliaria.portal_geo import actualizar_coordenadas_propiedad
                manual = (
                    self.cleaned_data.get('latitud') is not None
                    and self.cleaned_data.get('longitud') is not None
                )
                addr_changed = bool(
                    self._dir_prev
                    and (
                        (propiedad.direccion or '').strip() != self._dir_prev[0]
                        or (propiedad.ubicacion or '').strip() != self._dir_prev[1]
                    )
                )
                if not manual:
                    actualizar_coordenadas_propiedad(propiedad, force=addr_changed)
            except Exception:
                pass
        return propiedad
class PrecioForm(forms.ModelForm):
    class Meta:
        model = Precio
        fields = ['tipo_precio','precio_toma', 'precio_dia_toma', 'precio_por_dia', 'precio_total', 'ajuste_porcentaje']
        widgets = {
            'precio_toma': forms.TextInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_dia_toma': forms.TextInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_por_dia': forms.TextInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'precio_total': forms.TextInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'ajuste_porcentaje': forms.TextInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hacer que precio_total sea opcional solo si ya tiene un valor
        self.fields['precio_total'].required = False

    def clean_ajuste_porcentaje(self):
        ajuste = self.cleaned_data.get('ajuste_porcentaje')
        if ajuste < -100 or ajuste > 100:
            raise forms.ValidationError("El ajuste debe estar entre -100% y 100%.")
        return ajuste

    def clean(self):
        cleaned_data = super().clean()
        # Validar que si precio_total es ingresado, no se recalcula
        precio_total = cleaned_data.get('precio_total')
        if precio_total and precio_total <= 0:
            raise forms.ValidationError("El precio total debe ser positivo.")


    # def __init__(self, *args, **kwargs):
    #     super().__init__(*args, **kwargs)
    #     self.fields['imagenes'].widget.attrs.update({'class': 'form-control-file'})


# Formulario de Imágenes de Propiedad
# class PropiedadImagenForm(forms.ModelForm):
#     class Meta:
#         model = PropiedadImagen
#         fields = ['imagen']

# Formulario de Reserva
# inmobiliaria/forms.py

# forms.py

class ReservaForm(forms.ModelForm):
    class Meta:
        model = Reserva
        fields = ['propiedad', 'fecha_inicio', 'fecha_fin', 'vendedor', 'cliente']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date'}),

        }
class BuscarPropiedadesForm(forms.Form):
    origen = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ciudad de origen'
        })
    )
    destino = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ciudad de destino'
        })
    )
    fecha_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    fecha_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'form-control'
        })
    )
    tipo_inmueble = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_INMUEBLES, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    vista = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_VISTA, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    ambientes = forms.ChoiceField(
        required=True,
        choices=[
            ('1', '1 Ambiente'),
            ('2', '2 Ambientes'),
            ('3', '3 Ambientes'),
            ('4', '4 Ambientes'),
            ('5', '5 o más Ambientes'),
        ],
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    ver_todas = forms.BooleanField(
        required=False, 
        label="Ver todas las propiedades", 
        initial=False,
        widget=forms.CheckboxInput(attrs={
            'class': 'form-check-input'
        })
    )
    valoracion = forms.ChoiceField(
        choices=[('', 'Seleccione')] + TIPOS_VALORACION, 
        required=False,
        widget=forms.Select(attrs={
            'class': 'form-control'
        })
    )
    precio_min = forms.DecimalField(required=False, min_value=0)
    precio_max = forms.DecimalField(required=False, min_value=0)

    # Características booleanas
    amoblado = forms.BooleanField(required=False)
    cochera = forms.BooleanField(required=False)
    tv_smart = forms.BooleanField(required=False)
    wifi = forms.BooleanField(required=False)
    dependencia = forms.BooleanField(required=False)
    patio = forms.BooleanField(required=False)
    parrilla = forms.BooleanField(required=False)
    piscina = forms.BooleanField(required=False)
    reciclado = forms.BooleanField(required=False)
    a_estrenar = forms.BooleanField(required=False)
    terraza = forms.BooleanField(required=False)
    balcon = forms.BooleanField(required=False)
    baulera = forms.BooleanField(required=False)
    lavadero = forms.BooleanField(required=False)
    seguridad = forms.BooleanField(required=False)
    vista_al_Mar = forms.BooleanField(required=False)
    vista_panoramica = forms.BooleanField(required=False)
    apto_credito = forms.BooleanField(required=False)

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        
        if fecha_inicio and fecha_fin and fecha_inicio > fecha_fin:
            raise forms.ValidationError("La fecha de inicio no puede ser posterior a la fecha de fin.")
        
        return cleaned_data

class DisponibilidadForm(forms.ModelForm):
    forzar_superposicion = forms.BooleanField(
        required=False,
        initial=False,
        label='Forzar disponibilidad superpuesta',
        help_text=(
            'Permitir crear aunque ya exista disponibilidad o reserva en esas fechas. '
            'La propiedad saldrá para alquilar por día igual.'
        ),
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_forzar_superposicion'}),
    )

    class Meta:
        model = Disponibilidad
        fields = ['fecha_inicio', 'fecha_fin', 'asegurado', 'monto_asegurado', 'moneda_asegurado']
        widgets = {
            'fecha_inicio': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'fecha_fin': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'monto_asegurado': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Monto'}),
            'moneda_asegurado': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'asegurado': 'Marcar como asegurado',
            'monto_asegurado': 'Monto',
            'moneda_asegurado': 'Moneda',
        }

    def __init__(self, propiedad=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.propiedad = propiedad

    def clean(self):
        cleaned_data = super().clean()
        fecha_inicio = cleaned_data.get('fecha_inicio')
        fecha_fin = cleaned_data.get('fecha_fin')
        forzar = bool(cleaned_data.get('forzar_superposicion'))

        if fecha_inicio and fecha_fin:
            if fecha_fin < fecha_inicio:
                raise ValidationError('La fecha de fin debe ser posterior a la fecha de inicio')

            if self.propiedad and not forzar:
                # ✅ MEJORADO: Verificar superposición REAL (excluir fechas contiguas)
                # Fechas contiguas son PERMITIDAS (ej: 10-15 y 15-20)
                # Solo rechazar si hay superposición de MÁS de un día
                todas_disponibilidades = Disponibilidad.objects.filter(
                    propiedad=self.propiedad
                )
                
                # Si estamos editando, excluir la disponibilidad actual
                if self.instance.pk:
                    todas_disponibilidades = todas_disponibilidades.exclude(pk=self.instance.pk)
                
                # Verificar cada disponibilidad para detectar VERDADERA superposición
                solapamientos_reales = []
                for disp in todas_disponibilidades:
                    # Superposición REAL ocurre cuando comparten MÁS de un día
                    # Si solo se tocan en UN día (contiguas), es válido
                    if disp.fecha_fin > fecha_inicio and disp.fecha_inicio < fecha_fin:
                        # Hay superposición de al menos un día
                        solapamientos_reales.append(disp)
                
                if solapamientos_reales:
                    fechas_ocupadas = [
                        f"({d.fecha_inicio.strftime('%d/%m/%Y')} - {d.fecha_fin.strftime('%d/%m/%Y')})"
                        for d in solapamientos_reales
                    ]
                    raise ValidationError(
                        f'Las fechas se solapan con disponibilidades existentes: {", ".join(fechas_ocupadas)}. '
                        f'Marcá «Forzar disponibilidad superpuesta» para cargarla igual.'
                    )

        return cleaned_data

PrecioFormSet = modelformset_factory(
    Precio,
    form=PrecioForm,
    extra=0,  # No agrega formularios extra por defecto
    can_delete=True  # Para poder eliminar precios
)
class PropietarioBuscarForm(forms.Form):
    termino = forms.CharField(required=False, label='Buscar por nombre completo o DNI')

class InquilinoBuscarForm(forms.Form):
    termino = forms.CharField(required=False, label='Buscar nombre completo o DNI')

class SucursalForm(forms.ModelForm):
    class Meta:
        model = Sucursal
        fields = [
            'nombre',
            'direccion',
            'telefono',
            'email',
            'comision_minima_operacion',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la sucursal'
            }),
            'direccion': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Dirección de la sucursal'
            }),
            'telefono': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Email'
            }),
            'comision_minima_operacion': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0',
                'placeholder': '10000.00',
            }),
        }
        labels = {
            'nombre': 'Nombre de la Sucursal',
            'direccion': 'Dirección',
            'telefono': 'Teléfono',
            'email': 'Email',
            'comision_minima_operacion': 'Comisión mínima por productor ($)',
        }
        help_texts = {
            'comision_minima_operacion': (
                'Mínimo de comisión por productor (por línea). '
                'No se reparte entre productores. Poné 0 para desactivar el mínimo. '
                'No aplica a fichaje.'
            ),
        }

class LoginForm(forms.Form):
    username = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Usuario'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Contraseña'})
    )

class PropiedadSearchForm(forms.Form):
    query = forms.CharField(
        label='Buscar',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Buscar por dirección, ficha, propietario o vendedor'
        })
    )

class VentaPropiedadForm(forms.ModelForm):
    class Meta:
        model = VentaPropiedad
        fields = [
            'en_venta',
            'precio_venta',
            'precio_autorizacion',
            'estado',
            'precio_expensas',
            'escribania',
            'observaciones'
        ]
        widgets = {
            'observaciones': forms.Textarea(attrs={'rows': 3}),
            'escribania': forms.Textarea(attrs={'rows': 3}),
        }

class MovimientoCajaForm(forms.ModelForm):
    class Meta:
        model = MovimientoCaja
        fields = [
            'tipo',
            'tipo_comprobante',
            'numero_liquidacion',
            'concepto',
            'cuenta',
            'propiedad',
            'fecha_desde',
            'fecha_hasta',
            'monto_efectivo',
            'monto_cheque',
            'monto_tarjeta',
            'monto_deposito',
            'destino_deposito',
            'a_descontar',
            'sucursal',
            'empleado',
            'caja'
        ]

class RegistroForm(forms.ModelForm):
    class Meta:
        model = Registro
        fields = [
            'tipo',
            'tipo_comprobante',
            'fecha_comprobante',
            'liquidacion',
            'cuenta',
            'propiedad',
            'concepto',
            'fecha_desde',
            'fecha_hasta',
            'efectivo',
            'cheques',
            'tarjeta',
            'deposito',
            'qr',
            'tipo_descuento',
            'con_iva',
            'pasa_liquidaciones'
        ]
        widgets = {
            'tipo': forms.RadioSelect,
            'tipo_comprobante': forms.RadioSelect,
            'fecha_comprobante': forms.DateInput(attrs={'type': 'date'}),
            'fecha_desde': forms.DateInput(attrs={'type': 'date'}),
            'fecha_hasta': forms.DateInput(attrs={'type': 'date'}),
            'tipo_descuento': forms.RadioSelect,
        }

class ConceptoForm(forms.ModelForm):
    class Meta:
        model = Concepto
        fields = ['nombre']