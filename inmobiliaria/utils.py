from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os

def send_test_email(to_email):
    try:
        sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
        message = Mail(
            from_email='gonnetinterno@gmail.com',
            to_emails=to_email,
            subject='Test Email desde SendGrid',
            html_content='<p>Este es un email de prueba usando la API de SendGrid.</p>')
        
        response = sg.send(message)
        print(f'Status Code: {response.status_code}')
        print(f'Response Body: {response.body}')
        print(f'Response Headers: {response.headers}')
        return True
    except Exception as e:
        print(f'Error: {str(e)}')
        return False

def numero_a_palabras(numero):
    UNIDADES = ['', 'un', 'dos', 'tres', 'cuatro', 'cinco', 'seis', 'siete', 'ocho', 'nueve']
    DECENAS = ['', 'diez', 'veinte', 'treinta', 'cuarenta', 'cincuenta', 'sesenta', 'setenta', 'ochenta', 'noventa']
    DIEZ_A_VEINTE = ['diez', 'once', 'doce', 'trece', 'catorce', 'quince', 'dieciséis', 'diecisiete', 'dieciocho', 'diecinueve']
    CENTENAS = ['', 'ciento', 'doscientos', 'trescientos', 'cuatrocientos', 'quinientos', 'seiscientos', 'setecientos', 'ochocientos', 'novecientos']

    def _convertir_grupo(n, grupo):
        if n == '000':
            return ''
        
        centenas = int(n[0])
        decenas = int(n[1])
        unidades = int(n[2])
        
        texto = ''

        if centenas:
            if centenas == 1 and decenas == 0 and unidades == 0:
                texto = 'cien'
            else:
                texto = CENTENAS[centenas]

        if decenas or unidades:
            if texto:
                texto += ' '
            if decenas == 0:
                texto += UNIDADES[unidades]
            elif decenas == 1:
                texto += DIEZ_A_VEINTE[unidades]
            elif decenas == 2 and unidades == 0:
                texto += 'veinte'
            elif decenas == 2:
                texto += f'veinti{UNIDADES[unidades]}'
            else:
                texto += DECENAS[decenas]
                if unidades:
                    texto += f' y {UNIDADES[unidades]}'

        if grupo == 1 and n != '001':
            texto += ' mil'
        elif grupo == 2:
            if n == '001':
                texto = 'un millón'
            else:
                texto += ' millones'

        return texto

    if not numero:
        return 'cero pesos'

    numero = int(numero)
    if numero == 0:
        return 'cero pesos'

    # Convertir el número a string y rellenar con ceros a la izquierda
    str_numero = str(numero).zfill(9)
    
    millones = str_numero[0:3]
    miles = str_numero[3:6]
    unidades = str_numero[6:9]

    texto = ''
    
    if millones != '000':
        texto += _convertir_grupo(millones, 2)
    
    if miles != '000':
        if texto:
            texto += ' '
        texto += _convertir_grupo(miles, 1)
    
    if unidades != '000':
        if texto:
            texto += ' '
        texto += _convertir_grupo(unidades, 0)

    texto += ' pesos'
    
    # Capitalizar primera letra
    return texto.strip().capitalize()
