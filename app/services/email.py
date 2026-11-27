"""Envío de correos (bienvenida y recuperación de contraseña).

Modos, según las variables de entorno:
- SMTP_HOST definido: se envía por SMTP. Usuario y contraseña son opcionales (un agente de
  correo local como Postfix suele aceptar correo sin autenticación) y SMTP_SECURITY elige
  el cifrado: "starttls" (por defecto), "ssl" (puerto 465) o "none".
- Sin SMTP_HOST y con EMAILS_CONSOLE=true: los correos se imprimen en la consola (desarrollo).
- Si no hay ninguno de los dos, el envío está desactivado y la API lo dice en vez de fingir
  que ha enviado nada.
"""
import html
import logging
import os
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

logger = logging.getLogger(__name__)

APP_URL = os.getenv("APP_URL", "http://localhost:8000").rstrip("/")
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
SMTP_PORT = int(os.getenv("SMTP_PORT") or {"ssl": 465, "none": 25}.get(SMTP_SECURITY, 587))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAILS_FROM = os.getenv("EMAILS_FROM", "").strip() or SMTP_USER
EMAILS_FROM_NAME = os.getenv("EMAILS_FROM_NAME", "Bowling Club App")
EMAILS_CONSOLE = os.getenv("EMAILS_CONSOLE", "").strip().lower() in ("1", "true", "yes")

if SMTP_SECURITY not in ("starttls", "ssl", "none"):
    raise RuntimeError("SMTP_SECURITY debe ser starttls, ssl o none")
if SMTP_HOST and not EMAILS_FROM:
    raise RuntimeError("Con SMTP_HOST hay que definir EMAILS_FROM (o SMTP_USER) como remitente")


def emails_enabled() -> bool:
    return bool(SMTP_HOST) or EMAILS_CONSOLE


def _layout(body_html: str) -> str:
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #7c3aed;">🎳 Bowling Club App</h1>
        </div>
        {body_html}
      </body>
    </html>
    """


def _button(url: str, text: str) -> str:
    return (f'<div style="text-align: center; margin: 30px 0;"><a href="{html.escape(url)}" '
            'style="background-color: #7c3aed; color: white; padding: 12px 24px; text-decoration: none; '
            f'font-weight: bold; border-radius: 6px;">{html.escape(text)}</a></div>')


def send_email(to_email: str, subject: str, text: str, html_content: str) -> None:
    if not SMTP_HOST:
        if EMAILS_CONSOLE:
            print("================== CORREO (consola) ==================", flush=True)
            print(f"PARA: {to_email}\nASUNTO: {subject}\n\n{text}", flush=True)
            print("======================================================", flush=True)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((EMAILS_FROM_NAME, EMAILS_FROM))
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html_content, subtype="html")
    try:
        smtp_class = smtplib.SMTP_SSL if SMTP_SECURITY == "ssl" else smtplib.SMTP
        with smtp_class(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            if SMTP_SECURITY == "starttls":
                server.starttls()
            if SMTP_USER and SMTP_PASSWORD:
                server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        logger.info("Correo «%s» enviado a %s", subject, to_email)
    except Exception:
        logger.exception("No se ha podido enviar el correo «%s» a %s", subject, to_email)


def send_welcome_email(to_email: str, full_name: str) -> None:
    name = html.escape(full_name)
    send_email(
        to_email,
        f"¡Bienvenido/a a Bowling Club, {full_name}! 🎳",
        f"¡Hola {full_name}!\n\nYa tienes cuenta en Bowling Club. Entra en {APP_URL}/ para crear "
        "una sala o unirte a la de tus amigos.\n\n¡Nos vemos en las pistas!",
        _layout(f"""
        <p>¡Hola <strong>{name}</strong>!</p>
        <p>Ya tienes cuenta en Bowling Club. Crea una sala o pide a tus amigos que te inviten a la suya
        para empezar a apuntar partidas, plenos y semiplenos.</p>
        {_button(APP_URL + "/", "Entrar")}
        <p>¡Nos vemos en las pistas!</p>
        <hr style="border: none; border-top: 1px solid #eee; margin-top: 30px;">
        <p style="font-size: 12px; color: #888; text-align: center;">Si no has creado esta cuenta, puedes ignorar este correo.</p>
        """),
    )


def send_reset_password_email(to_email: str, full_name: str, token: str) -> None:
    name = html.escape(full_name)
    reset_url = f"{APP_URL}/reset-password?token={token}"
    send_email(
        to_email,
        "Cambia tu contraseña de Bowling Club 🎳",
        f"¡Hola {full_name}!\n\nPara elegir una contraseña nueva abre este enlace:\n{reset_url}\n\n"
        "Caduca en 20 minutos. Si no lo has pedido tú, ignora este correo.",
        _layout(f"""
        <p>¡Hola <strong>{name}</strong>!</p>
        <p>Hemos recibido una solicitud para cambiar tu contraseña. Pulsa el botón para elegir una nueva.</p>
        {_button(reset_url, "Elegir contraseña nueva")}
        <p style="font-size: 14px; color: #555;">El enlace caduca en 20 minutos. Si no lo has pedido tú,
        puedes ignorar este correo: tu contraseña no cambia.</p>
        """),
    )
