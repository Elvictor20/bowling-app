from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from .. import models, schemas, auth, database
from sqlalchemy import func, desc, asc

router = APIRouter(prefix="/api/rooms", tags=["rooms"])

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
def get_room_leaderboard(room_id: int, current_user: models.User = Depends(auth.get_current_user), db: Session = Depends(database.get_db)):
    # Check access
    membership = db.query(models.RoomMember).filter(models.RoomMember.room_id == room_id, models.RoomMember.user_id == current_user.id).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Not authorized")
        
    # Calculate leaderboard for this specific room
    results = db.query(
        models.User.id,
        models.User.full_name,
        func.sum(models.GameScore.score).label('total_score'),
        func.sum(models.GameScore.strikes).label('total_strikes'),
        func.sum(models.GameScore.spares).label('total_spares')
    ).join(models.GameScore, models.GameScore.user_id == models.User.id)\
     .join(models.Game, models.Game.id == models.GameScore.game_id)\
     .filter(models.Game.room_id == room_id)\
     .group_by(models.User.id, models.User.full_name)\
     .order_by(desc('total_score')).all()
     
    # It might miss users with 0 games, so let's get all members first, then map
    members = db.query(models.User).join(models.RoomMember).filter(models.RoomMember.room_id == room_id).all()
    
    leaderboard = []
    stats_map = {r.id: r for r in results}
    
    for member in members:
        if member.id in stats_map:
            st = stats_map[member.id]
            leaderboard.append({
                "user_id": member.id,
                "full_name": member.full_name,
                "total_score": st.total_score or 0,
                "total_strikes": st.total_strikes or 0,
                "total_spares": st.total_spares or 0
            })
        else:
            leaderboard.append({
                "user_id": member.id,
                "full_name": member.full_name,
                "total_score": 0,
                "total_strikes": 0,
                "total_spares": 0
            })
            
    # Sort again
    leaderboard.sort(key=lambda x: x["total_score"], reverse=True)
    
    # Assign rank
    for i, entry in enumerate(leaderboard):
        entry["rank"] = i + 1
        
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
                    "avg_strikes": round(avg, 1),
                    "total_strikes": stats["strikes"]
                }
                
    # Most Fit (Improvement in last 3 played games)
    most_fit = None
    max_improvement = -9999
    for m_id, pdata in players_data.items():
        real_scores = pdata["real_scores"]
        if len(real_scores) >= 2:
            # Check last 3 or less
            recent = real_scores[-3:]
            improvement = recent[-1] - recent[0]
            if improvement > max_improvement:
                max_improvement = improvement
                most_fit = {
                    "username": pdata["username"],
                    "improvement": improvement,
                    "last_score": recent[-1]
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

