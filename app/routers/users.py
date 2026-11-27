from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from .. import models, schemas, auth, database
from .auth import require_emails, start_password_reset
from sqlalchemy import func

router = APIRouter(prefix="/api/users", tags=["users"])

@router.get("/me", response_model=schemas.UserStats)
def get_user_me(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Calculate stats
    stats = db.query(
        func.sum(models.GameScore.score).label("total_score"),
        func.sum(models.GameScore.strikes).label("total_strikes"),
        func.sum(models.GameScore.spares).label("total_spares")
    ).filter(models.GameScore.user_id == current_user.id).first()

    nicknames = [n.nickname for n in current_user.nicknames]

    return schemas.UserStats(
        id=current_user.id,
        email=current_user.email,
        username=current_user.username,
        full_name=current_user.full_name,
        phone_number=current_user.phone_number,
        created_at=current_user.created_at,
        total_score=stats.total_score or 0,
        total_strikes=stats.total_strikes or 0,
        total_spares=stats.total_spares or 0,
        nicknames=nicknames
    )

@router.patch("/me", response_model=schemas.UserUpdateResponse)
def update_user_me(data: schemas.UserUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    if data.username and data.username != current_user.username:
        if db.query(models.User).filter(models.User.username == data.username).first():
            raise HTTPException(status_code=400, detail="Ese nombre de usuario ya está en uso")
        current_user.username = data.username

    if data.email and data.email != current_user.email:
        # El correo sirve para entrar y para recuperar la contraseña: pedimos la actual para cambiarlo
        if not data.current_password or not auth.verify_password(data.current_password, current_user.password_hash):
            raise HTTPException(status_code=400, detail="Para cambiar el correo escribe tu contraseña actual")
        if db.query(models.User).filter(models.User.email == data.email).first():
            raise HTTPException(status_code=400, detail="Ese correo ya está registrado")
        current_user.email = data.email
        # Un enlace de recuperación pedido para el correo anterior deja de valer
        current_user.reset_token = None
        current_user.reset_token_expires_at = None

    if data.full_name is not None:
        current_user.full_name = data.full_name
    if data.phone_number is not None:
        current_user.phone_number = data.phone_number or None

    db.commit()
    db.refresh(current_user)
    token = auth.token_for(current_user)
    return schemas.UserUpdateResponse(
        id=current_user.id, email=current_user.email, username=current_user.username,
        full_name=current_user.full_name, phone_number=current_user.phone_number,
        created_at=current_user.created_at, access_token=token,
    )

@router.post("/me/password-reset")
def request_my_password_reset(background_tasks: BackgroundTasks, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    """Envía al correo del usuario el mismo enlace que «¿Has olvidado tu contraseña?»."""
    require_emails()
    if not start_password_reset(current_user, background_tasks, db):
        raise HTTPException(status_code=429, detail="Ya te hemos enviado un enlace hace menos de un minuto. Revisa tu correo (también la carpeta de spam).")
    return {"message": f"Te hemos enviado un enlace a {current_user.email} para cambiar la contraseña. Caduca en 20 minutos."}
