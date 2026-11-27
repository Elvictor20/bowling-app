from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime
import hashlib
import secrets
from .. import models, schemas, auth, database
from ..services.email import emails_enabled, send_welcome_email, send_reset_password_email

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    db_user_email = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user_email:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    db_user_username = db.query(models.User).filter(models.User.username == user.username).first()
    if db_user_username:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    hashed_password = auth.get_password_hash(user.password)
    new_user = models.User(
        email=user.email,
        username=user.username,
        password_hash=hashed_password,
        full_name=user.full_name,
        phone_number=user.phone_number
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    if emails_enabled():
        background_tasks.add_task(send_welcome_email, new_user.email, new_user.full_name)
    
    return new_user

@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(database.get_db)):
    # form_data.username will contain the email
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"access_token": auth.token_for(user), "token_type": "bearer"}

RESET_LINK_MINUTES = 20
RESET_COOLDOWN = timedelta(minutes=1)  # como mucho un correo por minuto y cuenta


def hash_reset_token(token: str) -> str:
    # En la base de datos solo se guarda el hash: quien la lea no puede usar los enlaces
    return hashlib.sha256(token.encode()).hexdigest()


def require_emails():
    if not emails_enabled():
        raise HTTPException(status_code=503, detail="El envío de correos no está configurado en el servidor. Habla con el administrador.")


def start_password_reset(user: models.User, background_tasks: BackgroundTasks, db: Session) -> bool:
    """Genera un enlace de un solo uso y lo envía por correo. Devuelve False si se pidió otro hace menos de un minuto."""
    now = datetime.utcnow()
    if user.reset_token_expires_at and now < user.reset_token_expires_at - timedelta(minutes=RESET_LINK_MINUTES) + RESET_COOLDOWN:
        return False
    token = secrets.token_urlsafe(32)
    user.reset_token = hash_reset_token(token)
    user.reset_token_expires_at = now + timedelta(minutes=RESET_LINK_MINUTES)
    db.commit()
    background_tasks.add_task(send_reset_password_email, user.email, user.full_name, token)
    return True

@router.post("/forgot-password")
def forgot_password(req: schemas.ForgotPasswordRequest, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    require_emails()
    user = db.query(models.User).filter(models.User.email == req.email).first()
    if user:
        start_password_reset(user, background_tasks, db)

    # Always return same generic response to prevent email enumeration
    return {"message": "Si el correo está registrado, recibirás un enlace para restablecer tu contraseña."}

@router.post("/reset-password")
def reset_password(req: schemas.ResetPasswordRequest, db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(
        models.User.reset_token == hash_reset_token(req.token)
    ).first()
    
    if not user or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="El enlace no es válido o ha caducado")
        
    user.password_hash = auth.get_password_hash(req.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    db.commit()
    
    return {"message": "Contraseña actualizada correctamente"}
