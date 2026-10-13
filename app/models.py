import datetime
import enum
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, UniqueConstraint, JSON
from sqlalchemy.orm import relationship
from .database import Base

class RoleEnum(str, enum.Enum):
    OWNER = "OWNER"
    EDITOR = "EDITOR"
    VIEWER = "VIEWER"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    phone_number = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    reset_token = Column(String, index=True, nullable=True)
    reset_token_expires_at = Column(DateTime, nullable=True)

    nicknames = relationship("UserNickname", back_populates="user", cascade="all, delete-orphan")
    rooms_created = relationship("Room", back_populates="creator")
    room_memberships = relationship("RoomMember", back_populates="user", cascade="all, delete-orphan")
    games_recorded = relationship("Game", back_populates="recorder")
    scores = relationship("GameScore", back_populates="user", cascade="all, delete-orphan")

class UserNickname(Base):
    __tablename__ = "user_nicknames"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    nickname = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    user = relationship("User", back_populates="nicknames")

class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    creator = relationship("User", back_populates="rooms_created")
    members = relationship("RoomMember", back_populates="room", cascade="all, delete-orphan")
    games = relationship("Game", back_populates="room", cascade="all, delete-orphan")

class RoomMember(Base):
    __tablename__ = "room_members"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum(RoleEnum), default=RoleEnum.VIEWER, nullable=False)

    room = relationship("Room", back_populates="members")
    user = relationship("User", back_populates="room_memberships")

    __table_args__ = (UniqueConstraint('room_id', 'user_id', name='_room_user_uc'),)

class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    played_at = Column(DateTime, default=datetime.datetime.utcnow)

    room = relationship("Room", back_populates="games")
    recorder = relationship("User", back_populates="games_recorded")
    scores = relationship("GameScore", back_populates="game", cascade="all, delete-orphan")

class GameScore(Base):
    __tablename__ = "game_scores"

    id = Column(Integer, primary_key=True, index=True)
    game_id = Column(Integer, ForeignKey("games.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, nullable=False)
    strikes = Column(Integer, default=0)
    spares = Column(Integer, default=0)
    frames_data = Column(JSON, nullable=True)

    game = relationship("Game", back_populates="scores")
    user = relationship("User", back_populates="scores")
