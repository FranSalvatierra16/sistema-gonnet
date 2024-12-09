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
