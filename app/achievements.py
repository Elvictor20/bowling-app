"""Logros de cada jugador, calculados a partir de todas sus partidas (en cualquier sala).

Los logros de racha y de partida limpia necesitan el marcador tirada a tirada, así que solo
pueden conseguirse con partidas apuntadas en modo detallado.
"""
from sqlalchemy.orm import Session, selectinload

from . import models
from .routers.rooms import game_value


def _rolls(frames):
    """Tiradas en orden (X, /, -, dígitos) a partir de frames_data."""
    out = []
    for f in frames or []:
        for key in ("roll1", "roll2", "roll3"):
            r = (f.get(key) or "").upper()
            if r:
                out.append(r)
    return out


def has_turkey(frames) -> bool:
    run = 0
    for r in _rolls(frames):
        run = run + 1 if r == "X" else 0
        if run >= 3:
            return True
    return False


def is_clean_game(frames) -> bool:
    """Sin frames abiertos: cada frame es pleno o semipleno."""
    if not frames or len(frames) < 10:
        return False
    for f in frames[:10]:
        r1, r2 = (f.get("roll1") or "").upper(), (f.get("roll2") or "").upper()
        if r1 != "X" and r2 != "/":
            return False
    return True


# (id, icono, título, descripción, tipo, objetivo)
ACHIEVEMENTS = [
    ("first_game", "🎳", "Primera partida", "Juega tu primera partida", "games", 1),
    ("games_10", "🗓️", "Habitual", "Juega 10 partidas", "games", 10),
    ("games_50", "🏅", "Veterano", "Juega 50 partidas", "games", 50),
    ("score_150", "👍", "Buena tarde", "Haz 150 puntos o más en una partida", "score", 150),
    ("score_200", "💯", "Club de los 200", "Haz 200 puntos o más en una partida", "score", 200),
    ("score_250", "🚀", "Nivel pro", "Haz 250 puntos o más en una partida", "score", 250),
    ("perfect", "👑", "Partida perfecta", "Haz 300 puntos", "score", 300),
    ("strikes_5", "⚡", "Lluvia de plenos", "Haz 5 plenos en una partida", "strikes", 5),
    ("spares_5", "🧹", "Barrendero", "Haz 5 semiplenos en una partida", "spares", 5),
    ("turkey", "🦃", "Turkey", "Haz 3 plenos seguidos (modo detallado)", "turkey", 1),
    ("clean", "✨", "Partida limpia", "Ningún frame sin pleno o semipleno (modo detallado)", "clean", 1),
    ("win_1", "🏆", "Primera victoria", "Gana una partida contra al menos otro jugador", "wins", 1),
    ("win_10", "🥇", "Ganador nato", "Gana 10 partidas", "wins", 10),
]


def compute_achievements(user_id: int, db: Session) -> list:
    scores = (
        db.query(models.GameScore)
        .join(models.Game, models.Game.id == models.GameScore.game_id)
        .filter(models.GameScore.user_id == user_id)
        .options(selectinload(models.GameScore.game).selectinload(models.Game.scores))
        .order_by(models.Game.played_at, models.Game.id)
        .all()
    )

    # Para cada tipo, el progreso acumulado y la fecha en que se alcanzó cada objetivo
    games = wins = 0
    best = {"score": 0, "strikes": 0, "spares": 0, "turkey": 0, "clean": 0}
    reached = {}  # id de logro -> fecha

    def check(kind, current, when):
        for aid, _, _, _, k, goal in ACHIEVEMENTS:
            if k == kind and aid not in reached and current >= goal:
                reached[aid] = when

    for sc in scores:
        when = sc.game.played_at
        games += 1
        check("games", games, when)
        for kind, val in (("score", sc.score), ("strikes", sc.strikes), ("spares", sc.spares),
                          ("turkey", int(has_turkey(sc.frames_data))), ("clean", int(is_clean_game(sc.frames_data)))):
            best[kind] = max(best[kind], val)
            check(kind, best[kind], when)
        others = sc.game.scores
        if len(others) >= 2:
            top = max(game_value(o.score, o.strikes, o.spares) for o in others)
            if game_value(sc.score, sc.strikes, sc.spares) == top:
                wins += 1
                check("wins", wins, when)

    progress = {"games": games, "wins": wins, **best}
    return [
        {
            "id": aid, "icon": icon, "title": title, "description": desc,
            "unlocked": aid in reached, "unlocked_at": reached.get(aid),
            "progress": min(progress[kind], goal), "goal": goal,
        }
        for aid, icon, title, desc, kind, goal in ACHIEVEMENTS
    ]
