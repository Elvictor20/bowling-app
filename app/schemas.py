from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Any
from datetime import datetime
from .models import RoleEnum

# Users
class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: str
    phone_number: Optional[str] = None

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

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

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
    strikes: int = Field(ge=0, default=0)
    spares: int = Field(ge=0, default=0)
    nickname: Optional[str] = None
    frames_data: Optional[Any] = None

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
    rank: int
    user_id: int
    full_name: str
    total_score: int
    total_strikes: int
    total_spares: int

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
