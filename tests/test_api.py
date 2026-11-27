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


def _setup_room_with_two_players():
    client.post("/api/auth/register", json={"email": "a@test.com", "username": "a", "password": "pw", "full_name": "A"})
    client.post("/api/auth/register", json={"email": "b@test.com", "username": "b", "password": "pw", "full_name": "B"})
    token = client.post("/api/auth/login", data={"username": "a@test.com", "password": "pw"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    room_id = client.post("/api/rooms", json={"name": "Media"}, headers=headers).json()["id"]
    client.post(f"/api/rooms/{room_id}/members", json={"username": "b"}, headers=headers)
    return room_id, headers


def _play(room_id, headers, scores):
    res = client.post(f"/api/rooms/{room_id}/games", json={"scores": scores}, headers=headers)
    assert res.status_code == 200, res.text


def test_leaderboard_ranks_by_average_not_by_games_played():
    room_id, headers = _setup_room_with_two_players()
    # A juega 2 partidas buenas, B juega 5 peores: B suma más puntos pero A tiene mejor media
    for _ in range(2):
        _play(room_id, headers, [{"user_id": 1, "score": 180, "strikes": 4, "spares": 3}])
    for _ in range(5):
        _play(room_id, headers, [{"user_id": 2, "score": 120, "strikes": 1, "spares": 2}])

    lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers).json()
    assert [e["user_id"] for e in lb] == [1, 2]
    assert lb[0]["total_score"] < lb[1]["total_score"]
    # (180 + 5*3 + 10*4) = 235 por partida; (120 + 5*2 + 10*1) = 140 por partida
    assert lb[0]["average"] == 235.0
    assert lb[1]["average"] == 140.0
    assert lb[0]["games_played"] == 2 and lb[1]["games_played"] == 5
    assert [e["rank"] for e in lb] == [1, 2]


def test_one_great_game_beats_many_average_games():
    room_id, headers = _setup_room_with_two_players()
    # Sin mínimo de partidas: cuenta la media, no cuántas se han jugado
    _play(room_id, headers, [{"user_id": 2, "score": 220, "strikes": 7, "spares": 2}])
    for _ in range(4):
        _play(room_id, headers, [{"user_id": 1, "score": 130, "strikes": 2, "spares": 2}])

    lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers).json()
    assert [(e["user_id"], e["rank"]) for e in lb] == [(2, 1), (1, 2)]


def test_player_without_games_goes_last_without_rank():
    room_id, headers = _setup_room_with_two_players()
    _play(room_id, headers, [{"user_id": 2, "score": 90, "strikes": 0, "spares": 1}])
    lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers).json()
    assert [(e["user_id"], e["rank"]) for e in lb] == [(2, 1), (1, None)]


def test_member_without_games_has_zero_average():
    room_id, headers = _setup_room_with_two_players()
    lb = client.get(f"/api/rooms/{room_id}/leaderboard", headers=headers).json()
    assert all(e["games_played"] == 0 and e["average"] == 0 and e["rank"] is None for e in lb)


@pytest.mark.parametrize("score", [
    {"user_id": 1, "score": 300, "strikes": 13, "spares": 0},   # más de 12 plenos
    {"user_id": 1, "score": 200, "strikes": 0, "spares": 11},   # más de 10 semiplenos
    {"user_id": 1, "score": 250, "strikes": 9, "spares": 4},    # más de 12 en total
    {"user_id": 1, "score": 50, "strikes": 6, "spares": 0},     # 6 plenos valen al menos 60
])
def test_impossible_strikes_and_spares_are_rejected(score):
    room_id, headers = _setup_room_with_two_players()
    res = client.post(f"/api/rooms/{room_id}/games", json={"scores": [score]}, headers=headers)
    assert res.status_code == 422


def _setup_room_with_three_players():
    room_id, headers = _setup_room_with_two_players()
    client.post("/api/auth/register", json={"email": "c@test.com", "username": "c", "password": "pw", "full_name": "C"})
    client.post(f"/api/rooms/{room_id}/members", json={"username": "c"}, headers=headers)
    return room_id, headers


def _top(room_id, headers, by):
    res = client.get(f"/api/rooms/{room_id}/leaderboard?by={by}", headers=headers)
    assert res.status_code == 200, res.text
    return [(e["user_id"], e["rank"]) for e in res.json()]


def test_strikes_and_spares_tops_rank_by_totals():
    room_id, headers = _setup_room_with_three_players()
    _play(room_id, headers, [{"user_id": 1, "score": 200, "strikes": 6, "spares": 1},
                             {"user_id": 2, "score": 150, "strikes": 2, "spares": 6},
                             {"user_id": 3, "score": 120, "strikes": 2, "spares": 3}])
    _play(room_id, headers, [{"user_id": 2, "score": 160, "strikes": 3, "spares": 5}])
    # Plenos: A 6, B 5, C 2
    assert _top(room_id, headers, "strikes") == [(1, 1), (2, 2), (3, 3)]
    # Semiplenos: B 11, C 3, A 1
    assert _top(room_id, headers, "spares") == [(2, 1), (3, 2), (1, 3)]


def test_wins_top_counts_won_games_with_ties_and_skips_solo_games():
    room_id, headers = _setup_room_with_three_players()
    # A gana; B y C empatan a valor 150 y ganan los dos; partida en solitario de C no cuenta
    _play(room_id, headers, [{"user_id": 1, "score": 190, "strikes": 3, "spares": 2},
                             {"user_id": 2, "score": 140, "strikes": 1, "spares": 0}])
    _play(room_id, headers, [{"user_id": 2, "score": 140, "strikes": 1, "spares": 0},
                             {"user_id": 3, "score": 145, "strikes": 0, "spares": 1}])
    _play(room_id, headers, [{"user_id": 3, "score": 250, "strikes": 8, "spares": 1}])
    lb = client.get(f"/api/rooms/{room_id}/leaderboard?by=wins", headers=headers).json()
    assert {e["user_id"]: e["wins"] for e in lb} == {1: 1, 2: 1, 3: 1}
    # Todos empatan a 1 victoria: comparten el puesto 1
    assert [e["rank"] for e in lb] == [1, 1, 1]


def test_tied_players_share_rank_and_non_players_get_none():
    room_id, headers = _setup_room_with_three_players()
    _play(room_id, headers, [{"user_id": 1, "score": 100, "strikes": 2, "spares": 0},
                             {"user_id": 2, "score": 90, "strikes": 2, "spares": 0}])
    assert _top(room_id, headers, "strikes") == [(1, 1), (2, 1), (3, None)]


def test_unknown_top_is_rejected():
    room_id, headers = _setup_room_with_two_players()
    assert client.get(f"/api/rooms/{room_id}/leaderboard?by=potato", headers=headers).status_code == 422


def _login(email, password="pw"):
    res = client.post("/api/auth/login", data={"username": email, "password": password})
    return {"Authorization": f"Bearer {res.json()['access_token']}"} if res.status_code == 200 else None


def _register(username, email=None):
    client.post("/api/auth/register", json={"email": email or f"{username}@test.com", "username": username,
                                            "password": "pw", "full_name": username.title()})


def test_update_name_and_phone():
    _register("perfil")
    headers = _login("perfil@test.com")
    res = client.patch("/api/users/me", json={"full_name": "  Nombre Nuevo ", "phone_number": "600111222"}, headers=headers)
    assert res.status_code == 200, res.text
    me = client.get("/api/users/me", headers=headers).json()
    assert me["full_name"] == "Nombre Nuevo" and me["phone_number"] == "600111222"
    # Vaciar el teléfono lo borra
    client.patch("/api/users/me", json={"phone_number": ""}, headers=headers)
    assert client.get("/api/users/me", headers=headers).json()["phone_number"] is None


def test_change_username_returns_working_token():
    _register("viejo")
    headers = _login("viejo@test.com")
    res = client.patch("/api/users/me", json={"username": "nuevo"}, headers=headers)
    assert res.status_code == 200, res.text
    new_headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/api/users/me", headers=new_headers).json()["username"] == "nuevo"


def test_username_must_be_unique_and_valid():
    _register("uno"); _register("dos")
    headers = _login("dos@test.com")
    assert client.patch("/api/users/me", json={"username": "uno"}, headers=headers).status_code == 400
    assert client.patch("/api/users/me", json={"username": "con espacio"}, headers=headers).status_code == 422
    assert client.patch("/api/users/me", json={"username": "ab"}, headers=headers).status_code == 422
    assert client.patch("/api/users/me", json={"full_name": "   "}, headers=headers).status_code == 422


def test_change_email_requires_current_password():
    _register("correo"); _register("otro")
    headers = _login("correo@test.com")
    assert client.patch("/api/users/me", json={"email": "nuevo@test.com"}, headers=headers).status_code == 400
    assert client.patch("/api/users/me", json={"email": "nuevo@test.com", "current_password": "mal"}, headers=headers).status_code == 400
    assert client.patch("/api/users/me", json={"email": "otro@test.com", "current_password": "pw"}, headers=headers).status_code == 400
    assert client.patch("/api/users/me", json={"email": "no-es-correo", "current_password": "pw"}, headers=headers).status_code == 422
    res = client.patch("/api/users/me", json={"email": "nuevo@test.com", "current_password": "pw"}, headers=headers)
    assert res.status_code == 200, res.text
    assert _login("nuevo@test.com") is not None
    assert _login("correo@test.com") is None


def test_profile_password_reset_sends_link_to_own_email():
    _register("olvido")
    headers = _login("olvido@test.com")
    res = client.post("/api/users/me/password-reset", headers=headers)
    assert res.status_code == 200 and "olvido@test.com" in res.json()["message"]
    db = TestingSessionLocal()
    try:
        token = db.query(models.User).filter(models.User.username == "olvido").first().reset_token
    finally:
        db.close()
    assert client.post("/api/auth/reset-password", json={"token": token, "new_password": "nueva"}).status_code == 200
    assert _login("olvido@test.com", "nueva") is not None


def test_rejected_update_changes_nothing():
    _register("entero")
    headers = _login("entero@test.com")
    # El usuario es válido pero el correo falla por falta de contraseña: no se guarda nada
    res = client.patch("/api/users/me", json={"username": "cambiado", "email": "x@test.com"}, headers=headers)
    assert res.status_code == 400
    assert client.get("/api/users/me", headers=headers).json()["username"] == "entero"
