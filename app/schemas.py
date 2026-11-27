import re
from pydantic import BaseModel, Field, EmailStr, model_validator, field_validator
from typing import List, Optional, Any
from datetime import datetime
from .models import RoleEnum

# Users
def check_password(v: str) -> str:
    if not 8 <= len(v) <= 128:
        raise ValueError("La contraseña debe tener entre 8 y 128 caracteres")
    return v

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str
    phone_number: Optional[str] = None

    _password = field_validator("password")(check_password)

class UserResponse(BaseModel):
    id: int
    email: str
    username: str
    full_name: str
    phone_number: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class UserStats(UserResponse):
    total_score: int
    total_strikes: int
    total_spares: int
    nicknames: List[str]

class UserUpdate(BaseModel):
    """Campos editables del perfil; los que no se envían no cambian."""
    full_name: Optional[str] = None
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    current_password: Optional[str] = None  # obligatoria solo para cambiar el correo

    @field_validator("full_name", "username", "phone_number")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("full_name")
    @classmethod
    def check_full_name(cls, v):
        if v is not None and not 1 <= len(v) <= 60:
            raise ValueError("El nombre debe tener entre 1 y 60 caracteres")
        return v

    @field_validator("username")
    @classmethod
    def check_username(cls, v):
        if v is not None and not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", v):
            raise ValueError("El usuario debe tener entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo")
        return v

class UserUpdateResponse(UserResponse):
    access_token: str  # el token va ligado al usuario, así que se renueva al guardar

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    _password = field_validator("new_password")(check_password)

# Rooms
class RoomCreate(BaseModel):
    name: str

class RoomResponse(BaseModel):
    id: int
    name: str
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True

class RoomMemberCreate(BaseModel):
    username: str

class RoomMemberUpdate(BaseModel):
    role: RoleEnum

class RoomMemberResponse(BaseModel):
    id: int
    room_id: int
    user_id: int
    role: RoleEnum
    user: UserResponse

    class Config:
        from_attributes = True

# Games
class GameScoreCreate(BaseModel):
    user_id: int
    score: int = Field(ge=0, le=300)
    strikes: int = Field(ge=0, le=12, default=0)
    spares: int = Field(ge=0, le=10, default=0)
    nickname: Optional[str] = None
    frames_data: Optional[Any] = None

    @model_validator(mode="after")
    def check_strikes_and_spares(self):
        # Una partida tiene como mucho 12 plenos/semiplenos en total (9 frames + 3 tiradas del 10.º)
        # y cada pleno o semipleno vale al menos 10 puntos.
        marks = self.strikes + self.spares
        if marks > 12:
            raise ValueError("Una partida no puede tener más de 12 plenos y semiplenos en total")
        if self.score < 10 * marks:
            raise ValueError(f"Con {self.strikes} plenos y {self.spares} semiplenos la puntuación mínima es {10 * marks}")
        return self

class GameCreate(BaseModel):
    scores: List[GameScoreCreate]

class GameScoreResponse(BaseModel):
    id: int
    user_id: int
    score: int
    strikes: int
    spares: int
    frames_data: Optional[Any] = None
    user: Optional[UserResponse] = None

    class Config:
        from_attributes = True

class GameResponse(BaseModel):
    id: int
    room_id: int
    recorded_by: int
    played_at: datetime
    scores: List[GameScoreResponse]

    class Config:
        from_attributes = True

# Leaderboard
class LeaderboardEntry(BaseModel):
    rank: Optional[int] = None  # None si aún no ha jugado ninguna partida
    user_id: int
    full_name: str
    games_played: int
    average: float
    total_score: int
    total_strikes: int
    total_spares: int
    wins: int

class PlayerStatEntry(BaseModel):
    user_id: int
    username: str
    scores: List[Optional[int]]
    details: List[Optional[dict]]

class RoomRecord(BaseModel):
    highest_score: Optional[dict] = None
    strike_king: Optional[dict] = None
    most_fit: Optional[dict] = None

class RoomStatsResponse(BaseModel):
    labels: List[str]
    players: List[PlayerStatEntry]
    records: RoomRecord

# Auth
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None
