from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import math
from typing import List, Literal
from .. import models, schemas, auth, database
from sqlalchemy import func, desc, asc

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

# Ranking: media = (puntos + 5 por semipleno + 10 por pleno) / partidas jugadas
STRIKE_BONUS = 10
SPARE_BONUS = 5


def round1(x: float) -> float:
    """Redondeo a un decimal hacia arriba en los empates (2,45 → 2,5), igual que en la web."""
    return math.floor(x * 10 + 0.5) / 10


def game_value(score: int, strikes: int, spares: int) -> int:
    """Valor de una partida: decide quién gana cada partida y alimenta la puntuación del ranking."""
    return score + SPARE_BONUS * spares + STRIKE_BONUS * strikes


def ranking_average(total_score: int, strikes: int, spares: int, games: int) -> float:
    if games == 0:
        return 0.0
    return game_value(total_score, strikes, spares) / games


def count_wins(games) -> dict:
    """Partidas ganadas por jugador. Solo cuentan partidas de 2 o más jugadores; en un empate ganan todos los empatados."""
    wins = {}
    for game in games:
        if len(game.scores) < 2:
            continue
        values = {sc.user_id: game_value(sc.score, sc.strikes, sc.spares) for sc in game.scores}
        best = max(values.values())
        for user_id, value in values.items():
            if value == best:
                wins[user_id] = wins.get(user_id, 0) + 1
    return wins


# Hándicap como en las ligas de bolos: 90 % de lo que te falta para 200 de media
HANDICAP_BASE = 200
HANDICAP_PCT = 0.9


def handicap_for(average: float) -> int:
    return int(math.floor(HANDICAP_PCT * max(0, HANDICAP_BASE - average) + 0.5))


def compute_handicaps(games) -> dict:
    """Para cada jugador: hándicap actual y media de (puntos + hándicap).

    Cada partida usa el hándicap calculado con las partidas anteriores del jugador en la sala,
    así que lo que cuenta es superar tu propia media. La primera partida va sin hándicap.
    """
    history, adjusted = {}, {}
    for game in sorted(games, key=lambda g: (g.played_at, g.id)):
        for sc in game.scores:
            prev = history.setdefault(sc.user_id, [])
            hcp = handicap_for(sum(prev) / len(prev)) if prev else 0
            adjusted.setdefault(sc.user_id, []).append(sc.score + hcp)
            prev.append(sc.score)
    return {
        uid: {"handicap": handicap_for(sum(pts) / len(pts)),
              "handicap_average": round1(sum(adjusted[uid]) / len(adjusted[uid]))}
        for uid, pts in history.items()
    }


# Tops de la sala: campo por el que se ordena cada uno
LEADERBOARD_FIELDS = {"average": "average", "strikes": "total_strikes", "spares": "total_spares",
                      "wins": "wins", "handicap": "handicap_average"}

@router.post("", response_model=schemas.RoomResponse)
def create_room(room: schemas.RoomCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    new_room = models.Room(name=room.name, created_by=current_user.id)
    db.add(new_room)
    db.commit()
    db.refresh(new_room)
    
    # Add creator as OWNER
    member = models.RoomMember(room_id=new_room.id, user_id=current_user.id, role=models.RoleEnum.OWNER)
    db.add(member)
    db.commit()
    
    return new_room

@router.get("", response_model=List[schemas.RoomResponse])
def get_my_rooms(current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    rooms = db.query(models.Room).join(models.RoomMember).filter(models.RoomMember.user_id == current_user.id).all()
    return rooms

@router.get("/{room_id}", response_model=schemas.RoomResponse)
def get_room(room_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Check access
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
    room = db.query(models.Room).filter(models.Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return room

@router.post("/{room_id}/members", response_model=schemas.RoomMemberResponse)
def add_room_member(room_id: int, member_data: schemas.RoomMemberCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Check if current user is owner
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership or membership.role != models.RoleEnum.OWNER:
        raise HTTPException(status_code=403, detail="Not authorized to add members")
        
    user_to_add = db.query(models.User).filter(models.User.username == member_data.username).first()
    if not user_to_add:
        raise HTTPException(status_code=404, detail="User not found")
        
    existing = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == user_to_add.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="User already in room")
        
    new_member = models.RoomMember(room_id=room_id, user_id=user_to_add.id, role=models.RoleEnum.VIEWER)
    db.add(new_member)
    db.commit()
    db.refresh(new_member)
    return new_member

@router.get("/{room_id}/members", response_model=List[schemas.RoomMemberResponse])
def get_room_members(room_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
    members = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id).all()
    return members

@router.patch("/{room_id}/members/{user_id}", response_model=schemas.RoomMemberResponse)
def update_room_member(room_id: int, user_id: int, member_data: schemas.RoomMemberUpdate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership or membership.role != models.RoleEnum.OWNER:
        raise HTTPException(status_code=403, detail="Not authorized to modify members")
        
    target_member = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == user_id).first()
    if not target_member:
        raise HTTPException(status_code=404, detail="Member not found")
        
    target_member.role = member_data.role
    db.commit()
    db.refresh(target_member)
    return target_member

@router.get("/{room_id}/leaderboard", response_model=List[schemas.LeaderboardEntry])
def get_room_leaderboard(room_id: int, by: Literal["average", "strikes", "spares", "wins", "handicap"] = "average", current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Check access
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Totales de cada jugador en esta sala
    results = db.query(
        models.GameScore.user_id,
        func.count(models.GameScore.id).label('games_played'),
        func.sum(models.GameScore.score).label('total_score'),
        func.sum(models.GameScore.strikes).label('total_strikes'),
        func.sum(models.GameScore.spares).label('total_spares')
    ).join(models.Game, models.Game.id == models.GameScore.game_id)\
     .filter(models.Game.room_id == room_id)\
     .group_by(models.GameScore.user_id).all()
    stats_map = {r.user_id: r for r in results}
    room_games = db.query(models.Game).filter(models.Game.room_id == room_id).all()
    wins = count_wins(room_games)
    handicaps = compute_handicaps(room_games)

    # Todos los miembros, también los que aún no han jugado
    members = db.query(models.User).join(models.RoomMember).filter(models.RoomMember.room_id == room_id).all()

    leaderboard = []
    for member in members:
        st = stats_map.get(member.id)
        games = st.games_played if st else 0
        score = (st.total_score or 0) if st else 0
        strikes = (st.total_strikes or 0) if st else 0
        spares = (st.total_spares or 0) if st else 0
        leaderboard.append({
            "user_id": member.id,
            "full_name": member.full_name,
            "games_played": games,
            "average": round1(ranking_average(score, strikes, spares, games)),
            "total_score": score,
            "total_strikes": strikes,
            "total_spares": spares,
            "wins": wins.get(member.id, 0),
            "handicap": handicaps.get(member.id, {}).get("handicap", 0),
            "handicap_average": handicaps.get(member.id, {}).get("handicap_average", 0.0),
            "rank": None,
        })

    # Orden del top elegido; con el mismo valor se comparte puesto.
    # Quien aún no ha jugado va al final y sin puesto.
    field = LEADERBOARD_FIELDS[by]
    leaderboard.sort(key=lambda e: (e["games_played"] == 0, -e[field], e["games_played"] if by != "average" else -e["games_played"]))
    for i, entry in enumerate(leaderboard):
        if entry["games_played"]:
            prev = leaderboard[i - 1] if i else None
            entry["rank"] = prev["rank"] if prev and prev["rank"] and prev[field] == entry[field] else i + 1

    return leaderboard

@router.post("/{room_id}/games", response_model=schemas.GameResponse)
def add_game(room_id: int, game_data: schemas.GameCreate, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Room not found")
    if membership.role == models.RoleEnum.VIEWER:
        raise HTTPException(status_code=403, detail="No tienes permisos para registrar partidas en esta sala")
    new_game = models.Game(room_id=room_id, recorded_by=current_user.id)
    db.add(new_game)
    db.flush() # get new_game.id
    
    for sc in game_data.scores:
        score_entry = models.GameScore(
            game_id=new_game.id,
            user_id=sc.user_id,
            score=sc.score,
            strikes=sc.strikes,
            spares=sc.spares,
            frames_data=sc.frames_data
        )
        db.add(score_entry)
        
        if sc.nickname:
            nn = models.UserNickname(user_id=sc.user_id, nickname=sc.nickname)
            db.add(nn)
            
    db.commit()
    db.refresh(new_game)
    return new_game

@router.get("/{room_id}/games", response_model=List[schemas.GameResponse])
def get_games(room_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    games = db.query(models.Game).filter(models.Game.room_id == room_id).order_by(desc(models.Game.played_at)).all()
    return games

@router.get("/{room_id}/stats", response_model=schemas.RoomStatsResponse)
def get_room_stats(room_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    games = db.query(models.Game).filter(models.Game.room_id == room_id).order_by(asc(models.Game.played_at)).all()
    members = db.query(models.User).join(models.RoomMember).filter(models.RoomMember.room_id == room_id).all()
    
    labels = []
    players_data = {m.id: {"username": m.full_name, "scores": [], "details": [], "real_scores": []} for m in members}
    
    highest_score_val = -1
    highest_score_record = None
    
    strike_counts = {m.id: {"strikes": 0, "games": 0} for m in members}
    
    for i, game in enumerate(games):
        date_str = game.played_at.strftime("%d/%m")
        labels.append(f"P{i+1} ({date_str})")
        
        # Map scores for this game
        game_scores_map = {sc.user_id: sc for sc in game.scores}
        
        for m_id, pdata in players_data.items():
            sc = game_scores_map.get(m_id)
            if sc:
                pdata["scores"].append(sc.score)
                pdata["real_scores"].append(sc.score)
                pdata["details"].append({"strikes": sc.strikes, "spares": sc.spares})
                
                # Check highest score
                if sc.score > highest_score_val:
                    highest_score_val = sc.score
                    highest_score_record = {
                        "score": sc.score,
                        "username": pdata["username"],
                        "date": game.played_at.isoformat()
                    }
                    
                # Strikes aggregation
                strike_counts[m_id]["strikes"] += sc.strikes
                strike_counts[m_id]["games"] += 1
            else:
                pdata["scores"].append(None)
                pdata["details"].append(None)

    # Strike King
    strike_king = None
    max_strike_avg = -1
    for m_id, stats in strike_counts.items():
        if stats["games"] > 0:
            avg = stats["strikes"] / stats["games"]
            if avg > max_strike_avg:
                max_strike_avg = avg
                strike_king = {
                    "username": players_data[m_id]["username"],
                    "avg_strikes": round1(avg),
                    "total_strikes": stats["strikes"]
                }
                
    # Más en forma: quien más supera su propia media en las últimas 3 partidas (mínimo 4 partidas)
    most_fit = None
    for m_id, pdata in players_data.items():
        real_scores = pdata["real_scores"]
        if len(real_scores) >= 4:
            last3 = sum(real_scores[-3:]) / 3
            overall = sum(real_scores) / len(real_scores)
            improvement = round1(last3 - overall)
            if most_fit is None or improvement > most_fit["improvement"]:
                most_fit = {
                    "username": pdata["username"],
                    "improvement": improvement,
                    "last3_average": round1(last3),
                    "average": round1(overall),
                }
                
    players_result = []
    for m_id, pdata in players_data.items():
        players_result.append(schemas.PlayerStatEntry(
            user_id=m_id,
            username=pdata["username"],
            scores=pdata["scores"],
            details=pdata["details"]
        ))
        
    return schemas.RoomStatsResponse(
        labels=labels,
        players=players_result,
        records=schemas.RoomRecord(
            highest_score=highest_score_record,
            strike_king=strike_king,
            most_fit=most_fit
        )
    )

