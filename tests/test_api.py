import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
import sys

# Add app to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import app
from app.database import Base, get_db
from app import models, auth

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_bowling.db"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    # No teardown needed as we drop before each

def test_register_and_login():
    # Register
    res = client.post("/api/auth/register", json={
        "email": "test@test.com",
        "username": "testuser",
        "password": "testpassword",
        "full_name": "Test User",
        "phone_number": "123456789"
    })
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"

    # Login
    res2 = client.post("/api/auth/login", data={
        "username": "test@test.com",
        "password": "testpassword"
    })
    assert res2.status_code == 200
    assert "access_token" in res2.json()

def test_create_room_and_leaderboard():
    # Setup users
    client.post("/api/auth/register", json={"email": "user1@test.com", "username": "user1", "password": "pw", "full_name": "User 1"})
    client.post("/api/auth/register", json={"email": "user2@test.com", "username": "user2", "password": "pw", "full_name": "User 2"})

    token1 = client.post("/api/auth/login", data={"username": "user1@test.com", "password": "pw"}).json()["access_token"]
    
    # Create room
    headers = {"Authorization": f"Bearer {token1}"}
    res = client.post("/api/rooms", json={"name": "Test Room"}, headers=headers)
    assert res.status_code == 200
    room_id = res.json()["id"]

    # Add member
    res_add = client.post(f"/api/rooms/{room_id}/members", json={"username": "user2"}, headers=headers)
    assert res_add.status_code == 200

    # Add game
    game_payload = {
        "scores": [
            {"user_id": 1, "score": 200, "strikes": 5, "spares": 2, "nickname": "Pro"},
            {"user_id": 2, "score": 150, "strikes": 2, "spares": 4}
        ]
    }
    res_game = client.post(f"/api/rooms/{room_id}/games", json=game_payload, headers=headers)
    assert res_game.status_code == 200

    # Get Leaderboard
    res_lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers)
    assert res_lb.status_code == 200
    lb = res_lb.json()
    assert len(lb) == 2
    assert lb[0]["user_id"] == 1
    assert lb[0]["total_score"] == 200
    assert lb[1]["user_id"] == 2
    assert lb[1]["total_score"] == 150

    # Get User Profile to check nickname
    res_me = client.get("/api/users/me", headers=headers)
    assert res_me.status_code == 200
    assert "Pro" in res_me.json()["nicknames"]

def test_perfect_game_and_history():
    # Setup users
    client.post("/api/auth/register", json={"email": "pro@test.com", "username": "pro", "password": "pw", "full_name": "Pro Bowler"})
    token = client.post("/api/auth/login", data={"username": "pro@test.com", "password": "pw"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    res_room = client.post("/api/rooms", json={"name": "Tournament Room"}, headers=headers)
    room_id = res_room.json()["id"]

    # Perfect Game
    frames_perfect = []
    for i in range(9):
        frames_perfect.append({"roll1": "X", "roll2": "", "roll3": "", "score": (i+1)*30})
    frames_perfect.append({"roll1": "X", "roll2": "X", "roll3": "X", "score": 300})
    
    game_payload_perfect = {
        "scores": [
            {
                "user_id": 1,
                "score": 300,
                "strikes": 12,
                "spares": 0,
                "frames_data": frames_perfect
            }
        ]
    }
    res_game1 = client.post(f"/api/rooms/{room_id}/games", json=game_payload_perfect, headers=headers)
    assert res_game1.status_code == 200

    # All Spares (5 and /) -> 150 points
    frames_spares = []
    running = 0
    for i in range(9):
        running += 15
        frames_spares.append({"roll1": "5", "roll2": "/", "roll3": "", "score": running})
    frames_spares.append({"roll1": "5", "roll2": "/", "roll3": "5", "score": 150})
    
    game_payload_spares = {
        "scores": [
            {
                "user_id": 1,
                "score": 150,
                "strikes": 0,
                "spares": 10,
                "frames_data": frames_spares
            }
        ]
    }
    res_game2 = client.post(f"/api/rooms/{room_id}/games", json=game_payload_spares, headers=headers)
    assert res_game2.status_code == 200

    # History Aggregation
    res_history = client.get(f"/api/rooms/{room_id}/games", headers=headers)
    assert res_history.status_code == 200
    games = res_history.json()
    assert len(games) == 2
    
    # We should calculate the aggregations over the scores (simulating frontend check)
    g1 = games[0] # The latest one is the all-spares
    g2 = games[1] # The perfect game
    
    # Assert perfectly stored frames
    assert g1["scores"][0]["frames_data"][-1]["score"] == 150
    assert g2["scores"][0]["frames_data"][-1]["score"] == 300
    
    # Check aggregation of Room Leaderboard
    res_lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers)
    lb = res_lb.json()
    assert lb[0]["total_score"] == 450
    assert lb[0]["total_strikes"] == 12
    assert lb[0]["total_spares"] == 10
    
    # Test Stats endpoint
    res_stats = client.get(f"/api/rooms/{room_id}/stats", headers=headers)
    assert res_stats.status_code == 200
    stats = res_stats.json()
    
    # Validate chronological order (game1 was perfect, game2 was spares)
    assert len(stats["labels"]) == 2
    
    player_stats = next(p for p in stats["players"] if p["user_id"] == 1)
    assert player_stats["scores"] == [300, 150]
    
    assert stats["records"]["highest_score"]["score"] == 300
    assert stats["records"]["strike_king"]["total_strikes"] == 12
    # Most fit requires 2 games, it went from 300 to 150, so improvement is -150
    assert stats["records"]["most_fit"]["improvement"] == -150

def test_password_recovery_flow():
    # Setup user
    email = "recovery@test.com"
    client.post("/api/auth/register", json={"email": email, "username": "recovery_user", "password": "old_password", "full_name": "Recovery"})
    
    # 1. Forgot password - valid email
    res_forgot = client.post("/api/auth/forgot-password", json={"email": email})
    assert res_forgot.status_code == 200
    assert "recibirás un enlace" in res_forgot.json()["message"]
    
    # Check that token was generated in DB
    db_gen = TestingSessionLocal()
    try:
        user = db_gen.query(models.User).filter(models.User.email == email).first()
        assert user.reset_token is not None
        assert user.reset_token_expires_at is not None
        
        token = user.reset_token
        
        # 2. Reset password - invalid token
        res_reset_invalid = client.post("/api/auth/reset-password", json={"token": "invalid_token", "new_password": "new_password"})
        assert res_reset_invalid.status_code == 400
        
        # 3. Reset password - valid token
        res_reset = client.post("/api/auth/reset-password", json={"token": token, "new_password": "new_password"})
        assert res_reset.status_code == 200
        
        # Ensure token is cleared
        db_gen.refresh(user)
        assert user.reset_token is None
    finally:
        db_gen.close()
    
    # 4. Old password should fail
    res_login_old = client.post("/api/auth/login", data={"username": email, "password": "old_password"})
    assert res_login_old.status_code == 401
    
    # 5. New password should work
    res_login_new = client.post("/api/auth/login", data={"username": email, "password": "new_password"})
    assert res_login_new.status_code == 200
    assert "access_token" in res_login_new.json()
