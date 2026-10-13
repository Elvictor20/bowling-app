from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from .. import models, schemas, auth, database
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
