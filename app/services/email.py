import os
import smtplib
from email.message import EmailMessage
import logging

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = os.getenv("SMTP_PORT")
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAILS_FROM_NAME = os.getenv("EMAILS_FROM_NAME", "Bowling Club App")

def send_welcome_email(to_email: str, full_name: str):
    subject = f"¡Bienvenido/a al mundo de los bolos, {full_name}! 🎳"
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2563eb;">🎳 Bowling Club App</h1>
        </div>
        
        <p>¡Hola <strong>{full_name}</strong>!</p>
        
        <p>Estamos muy emocionados de darte la bienvenida a nuestra comunidad. El mundo de los bolos te espera y con nuestra plataforma podrás llevar el registro de tus mejores partidas, plenos (strikes) y semiplenos (spares).</p>
        
        <p>Ya puedes unirte a las salas de tus amigos o crear la tuya propia para empezar a registrar resultados.</p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="http://localhost:8000/login" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; font-weight: bold; border-radius: 6px;">Iniciar Sesión</a>
        </div>
        
        <p>¡Nos vemos en las pistas!</p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 30px;">
        <p style="font-size: 12px; color: #888; text-align: center;">Si no has creado esta cuenta, puedes ignorar este correo.</p>
      </body>
    </html>
    """

    if not SMTP_HOST or not SMTP_PORT or not SMTP_USER or not SMTP_PASSWORD:
        print("================== MOCK EMAIL ==================", flush=True)
        print(f"TO: {to_email}", flush=True)
        print(f"SUBJECT: {subject}", flush=True)
        print("BODY (HTML):", flush=True)
        print(html_content, flush=True)
        print("================================================", flush=True)
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{EMAILS_FROM_NAME} <{SMTP_USER}>"
    msg['To'] = to_email
    
    msg.set_content(f"¡Hola {full_name}!\n\nBienvenido a Bowling Club App. Inicia sesión para registrar tus partidas.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            logger.info(f"Email sent successfully to {to_email}")
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")

def send_reset_password_email(to_email: str, full_name: str, token: str, domain: str = "http://localhost:8000"):
    subject = "Restablece tu contraseña - Bowling App 🎳"
    reset_url = f"{domain}/reset-password?token={token}"
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #2563eb;">🎳 Bowling Club App</h1>
        </div>
        
        <p>¡Hola <strong>{full_name}</strong>!</p>
        
        <p>Hemos recibido una solicitud para restablecer tu contraseña. Haz clic en el botón siguiente para elegir una nueva.</p>
        
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background-color: #2563eb; color: white; padding: 12px 24px; text-decoration: none; font-weight: bold; border-radius: 6px;">Actualizar Contraseña</a>
        </div>
        
        <p style="font-size: 14px; color: #555;">Este enlace caducará en 20 minutos. Si no has solicitado este cambio, puedes ignorar este correo de forma segura.</p>
        
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 30px;">
        <p style="font-size: 12px; color: #888; text-align: center;">Bowling App</p>
      </body>
    </html>
    """

    if not SMTP_HOST or not SMTP_PORT or not SMTP_USER or not SMTP_PASSWORD:
        print("================== MOCK EMAIL ==================", flush=True)
        print(f"TO: {to_email}", flush=True)
        print(f"SUBJECT: {subject}", flush=True)
        print(f"LINK: {reset_url}", flush=True)
        print("BODY (HTML):", flush=True)
        print(html_content, flush=True)
        print("================================================", flush=True)
        return

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f"{EMAILS_FROM_NAME} <{SMTP_USER}>"
    msg['To'] = to_email
    
    msg.set_content(f"¡Hola {full_name}!\n\nHaz clic aquí para restablecer tu contraseña: {reset_url}\nEl enlace expira en 20 minutos.")
    msg.add_alternative(html_content, subtype='html')

    try:
        with smtplib.SMTP(SMTP_HOST, int(SMTP_PORT)) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
            logger.info(f"Reset email sent successfully to {to_email}")
    except Exception as e:
        logger.error(f"Error sending reset email to {to_email}: {e}")
