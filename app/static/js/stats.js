/*
 * Cálculos de la pestaña Estadísticas. Funciones puras: reciben las partidas tal como las
 * devuelve GET /api/rooms/{id}/games (cada una con played_at y scores[] con user) y los
 * miembros de GET /api/rooms/{id}/members. No tocan el DOM, así que se prueban con node.
 */
(function (root) {
  'use strict';

  const STRIKE_BONUS = 10;
  const SPARE_BONUS = 5;

  // Valor de una partida: decide quién gana y alimenta la puntuación del ranking (igual que el servidor)
  const value = s => s.score + SPARE_BONUS * s.spares + STRIKE_BONUS * s.strikes;
  const mean = xs => xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null;
  const round1 = x => x === null ? null : Math.round(x * 10) / 10;
  const pad = n => String(n).padStart(2, '0');

  function parseDate(iso) {
    // El servidor guarda fechas sin zona (UTC); se interpretan como hora local igual que el resto de la app
    return new Date(iso);
  }
  const monthKey = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}`;
  const dayKey = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

  // Una «noche» va de 6:00 a 6:00: una partida a las 00:30 cuenta para la noche anterior
  function nightKey(iso) {
    const d = parseDate(iso);
    return dayKey(new Date(d.getTime() - 6 * 3600 * 1000));
  }

  const sortAsc = games => games.slice().sort((a, b) => (a.played_at < b.played_at ? -1 : a.played_at > b.played_at ? 1 : a.id - b.id));

  function filterGames(games, period, now = new Date()) {
    const asc = sortAsc(games);
    if (period === 'last5') return asc.slice(-5);
    if (period === 'last10') return asc.slice(-10);
    if (period === 'month') return asc.filter(g => monthKey(parseDate(g.played_at)) === monthKey(now));
    return asc;
  }

  // Clasificación de una partida; empates comparten puesto
  function gameRanking(game) {
    const scores = game.scores.slice().sort((a, b) => value(b) - value(a) || b.score - a.score);
    scores.forEach((s, i) => {
      const prev = scores[i - 1];
      s.rank = prev && value(prev) === value(s) ? prev.rank : i + 1;
    });
    return scores;
  }

  // Ganadores: quien más valor hace; partidas de un solo jugador no cuentan
  function winnersOf(game) {
    if (game.scores.length < 2) return [];
    const best = Math.max(...game.scores.map(value));
    return game.scores.filter(s => value(s) === best).map(s => s.user_id);
  }

  const players = members => members.map(m => ({ id: m.user_id, name: m.user.full_name }));
  const scoreOf = (game, uid) => game.scores.find(s => s.user_id === uid) || null;

  // Media móvil de las últimas n partidas jugadas por cada uno (las ausencias no cuentan)
  function rollingAvg(values, n = 3) {
    const played = [];
    return values.map(v => {
      if (v === null) return null;
      played.push(v);
      return round1(mean(played.slice(-n)));
    });
  }

  function series(games, members, mode = 'points') {
    const labels = games.map((g, i) => {
      const d = parseDate(g.played_at);
      return `P${i + 1} · ${pad(d.getDate())}/${pad(d.getMonth() + 1)}`;
    });
    const data = {};
    players(members).forEach(p => {
      const raw = games.map(g => { const s = scoreOf(g, p.id); return s ? s.score : null; });
      data[p.id] = mode === 'trend' ? rollingAvg(raw) : raw;
    });
    return { labels, data };
  }

  // Posición en el top de Puntuación tras cada partida (null hasta que juega)
  function rankingRace(games, members) {
    const acc = {};
    const out = {};
    players(members).forEach(p => { out[p.id] = []; });
    games.forEach(g => {
      g.scores.forEach(s => {
        const a = acc[s.user_id] || (acc[s.user_id] = { v: 0, n: 0 });
        a.v += value(s); a.n += 1;
      });
      const table = Object.entries(acc).map(([uid, a]) => ({ uid: +uid, avg: a.v / a.n }))
        .sort((x, y) => y.avg - x.avg);
      const pos = {};
      table.forEach((r, i) => { pos[r.uid] = i && table[i - 1].avg === r.avg ? pos[table[i - 1].uid] : i + 1; });
      Object.keys(out).forEach(uid => out[uid].push(pos[uid] || null));
    });
    return out;
  }

  function cumulativeWins(games, members) {
    const out = {};
    const count = {};
    players(members).forEach(p => { out[p.id] = []; count[p.id] = 0; });
    games.forEach(g => {
      winnersOf(g).forEach(uid => { if (uid in count) count[uid] += 1; });
      Object.keys(out).forEach(uid => out[uid].push(count[uid]));
    });
    return out;
  }

  function marksPerGame(games, members) {
    return players(members).map(p => {
      const sc = games.map(g => scoreOf(g, p.id)).filter(Boolean);
      return {
        id: p.id, name: p.name, games: sc.length,
        strikes: round1(mean(sc.map(s => s.strikes))), spares: round1(mean(sc.map(s => s.spares))),
      };
    }).filter(r => r.games > 0);
  }

  // Histograma por tramos de 20 puntos
  function distribution(scores, step = 20) {
    const buckets = [];
    for (let lo = 0; lo < 300; lo += step) buckets.push({ lo, hi: Math.min(lo + step - 1, 300), count: 0 });
    buckets[buckets.length - 1].hi = 300;
    scores.forEach(v => { buckets[Math.min(Math.floor(v / step), buckets.length - 1)].count += 1; });
    // Recorta los tramos vacíos de los extremos para que la gráfica se lea en el móvil
    let a = 0, b = buckets.length - 1;
    while (a < b && !buckets[a].count) a++;
    while (b > a && !buckets[b].count) b--;
    return buckets.slice(a, b + 1);
  }

  function monthlyAverages(games, members) {
    const months = [...new Set(games.map(g => monthKey(parseDate(g.played_at))))].sort();
    const data = {};
    players(members).forEach(p => {
      data[p.id] = months.map(m => round1(mean(games
        .filter(g => monthKey(parseDate(g.played_at)) === m)
        .map(g => scoreOf(g, p.id)).filter(Boolean).map(s => s.score))));
    });
    return { months, data };
  }

  function stdev(xs) {
    if (xs.length < 2) return null;
    const m = mean(xs);
    return Math.sqrt(mean(xs.map(x => (x - m) ** 2)));
  }

  function consistencyLabel(sd) {
    if (sd === null) return 'Faltan partidas';
    if (sd < 15) return 'Muy regular';
    if (sd < 30) return 'Regular';
    if (sd < 45) return 'Irregular';
    return 'Montaña rusa';
  }

  function playerCard(games, uid) {
    const mine = games.filter(g => scoreOf(g, uid));
    const sc = mine.map(g => scoreOf(g, uid));
    const pts = sc.map(s => s.score);
    if (!sc.length) return { games: 0 };
    const wins = mine.filter(g => winnersOf(g).includes(uid)).length;
    const multi = mine.filter(g => g.scores.length > 1).length;
    const last3 = mean(pts.slice(-3));
    const sd = stdev(pts);
    const bestIdx = pts.indexOf(Math.max(...pts));
    const worstIdx = pts.indexOf(Math.min(...pts));
    return {
      games: sc.length,
      avgPoints: round1(mean(pts)),
      avgValue: round1(mean(sc.map(value))),
      best: { score: pts[bestIdx], date: mine[bestIdx].played_at },
      worst: { score: pts[worstIdx], date: mine[worstIdx].played_at },
      stdev: round1(sd),
      consistency: consistencyLabel(sd),
      trend: pts.length >= 4 ? round1(last3 - mean(pts)) : null,
      wins, winPct: multi ? Math.round((wins / multi) * 100) : null,
      strikesPerGame: round1(mean(sc.map(s => s.strikes))),
      sparesPerGame: round1(mean(sc.map(s => s.spares))),
      last5: pts.slice(-5),
      scores: pts,
    };
  }

  function headToHead(games, a, b) {
    const both = games.filter(g => scoreOf(g, a) && scoreOf(g, b));
    let winsA = 0, winsB = 0, ties = 0;
    const recent = both.map(g => {
      const sa = scoreOf(g, a), sb = scoreOf(g, b);
      const d = value(sa) - value(sb);
      if (d > 0) winsA++; else if (d < 0) winsB++; else ties++;
      return { date: g.played_at, a: sa.score, b: sb.score, winner: d > 0 ? a : d < 0 ? b : null };
    });
    const ptsA = both.map(g => scoreOf(g, a).score), ptsB = both.map(g => scoreOf(g, b).score);
    return {
      games: both.length, winsA, winsB, ties,
      avgA: round1(mean(ptsA)), avgB: round1(mean(ptsB)),
      bestA: ptsA.length ? Math.max(...ptsA) : null, bestB: ptsB.length ? Math.max(...ptsB) : null,
      recent: recent.slice(-5).reverse(),
    };
  }

  function records(games, members) {
    const names = Object.fromEntries(players(members).map(p => [p.id, p.name]));
    let highest = null, lowest = null, mostStrikes = null, mostSpares = null;
    games.forEach(g => g.scores.forEach(s => {
      const r = k => ({ user_id: s.user_id, name: names[s.user_id] || s.user?.full_name, value: s[k], date: g.played_at });
      if (!highest || s.score > highest.value) highest = r('score');
      if (!lowest || s.score < lowest.value) lowest = r('score');
      if (!mostStrikes || s.strikes > mostStrikes.value) mostStrikes = r('strikes');
      if (!mostSpares || s.spares > mostSpares.value) mostSpares = r('spares');
    }));
    const played = players(members).map(p => ({ user_id: p.id, name: p.name, value: games.filter(g => scoreOf(g, p.id)).length }))
      .sort((x, y) => y.value - x.value);
    const mostGames = played.length && played[0].value ? played[0] : null;

    // Mayor mejora de un mes al siguiente (media de puntos), entre meses en los que jugó
    const { months, data } = monthlyAverages(games, members);
    let improvement = null;
    Object.entries(data).forEach(([uid, avgs]) => {
      let prev = null;
      avgs.forEach((v, i) => {
        if (v === null) return;
        if (prev && (!improvement || v - prev.v > improvement.value)) {
          improvement = { user_id: +uid, name: names[uid], value: round1(v - prev.v), from: months[prev.i], to: months[i] };
        }
        prev = { v, i };
      });
    });
    if (improvement && improvement.value <= 0) improvement = null;
    return { highest, lowest, mostStrikes, mostSpares, mostGames, improvement };
  }

  function strikeKing(games, members) {
    let best = null;
    players(members).forEach(p => {
      const sc = games.map(g => scoreOf(g, p.id)).filter(Boolean);
      if (!sc.length) return;
      const avg = mean(sc.map(s => s.strikes));
      if (!best || avg > best.value) best = { user_id: p.id, name: p.name, value: round1(avg), total: sc.reduce((a, s) => a + s.strikes, 0) };
    });
    return best;
  }

  // Más en forma: quien más supera su propia media en las últimas 3 partidas (mínimo 4 partidas)
  function mostFit(games, members) {
    let best = null;
    players(members).forEach(p => {
      const pts = games.map(g => scoreOf(g, p.id)).filter(Boolean).map(s => s.score);
      if (pts.length < 4) return;
      const diff = mean(pts.slice(-3)) - mean(pts);
      if (!best || diff > best.value) best = { user_id: p.id, name: p.name, value: round1(diff), last3: round1(mean(pts.slice(-3))), overall: round1(mean(pts)) };
    });
    return best;
  }

  function streaks(games, members) {
    return players(members).map(p => {
      const mine = games.filter(g => scoreOf(g, p.id));
      const pts = mine.map(g => scoreOf(g, p.id).score);
      const avg = mean(pts);
      let cur = 0, best = 0;
      mine.filter(g => g.scores.length > 1).forEach(g => {
        cur = winnersOf(g).includes(p.id) ? cur + 1 : 0;
        best = Math.max(best, cur);
      });
      let above = 0;
      for (let i = pts.length - 1; i >= 0 && pts[i] > avg; i--) above++;
      return { user_id: p.id, name: p.name, games: mine.length, currentWins: cur, bestWins: best, aboveAvg: above, onFire: above >= 3 || cur >= 3 };
    }).filter(r => r.games > 0);
  }

  function nights(games, members) {
    const names = Object.fromEntries(players(members).map(p => [p.id, p.name]));
    const groups = {};
    games.forEach(g => { (groups[nightKey(g.played_at)] = groups[nightKey(g.played_at)] || []).push(g); });
    return Object.entries(groups).sort((a, b) => (a[0] < b[0] ? 1 : -1)).map(([key, gs]) => {
      const rows = {};
      gs.forEach(g => {
        const winners = winnersOf(g);
        g.scores.forEach(s => {
          const r = rows[s.user_id] || (rows[s.user_id] = { user_id: s.user_id, name: names[s.user_id] || s.user?.full_name, games: 0, v: 0, pts: 0, wins: 0, strikes: 0, spares: 0, best: 0 });
          r.games++; r.v += value(s); r.pts += s.score; r.strikes += s.strikes; r.spares += s.spares;
          r.best = Math.max(r.best, s.score);
          if (winners.includes(s.user_id)) r.wins++;
        });
      });
      const ranking = Object.values(rows).map(r => ({ ...r, avgValue: round1(r.v / r.games), avgPoints: round1(r.pts / r.games) }))
        .sort((a, b) => b.avgValue - a.avgValue || b.wins - a.wins);
      ranking.forEach((r, i) => { r.rank = i && ranking[i - 1].avgValue === r.avgValue ? ranking[i - 1].rank : i + 1; });
      return { key, games: gs.length, ranking, winner: ranking.length > 1 ? ranking[0] : null };
    });
  }

  const api = {
    STRIKE_BONUS, SPARE_BONUS, value, mean, round1, nightKey, monthKey, dayKey, sortAsc, filterGames,
    gameRanking, winnersOf, rollingAvg, series, rankingRace, cumulativeWins, marksPerGame, distribution,
    monthlyAverages, playerCard, headToHead, records, strikeKing, mostFit, streaks, nights, consistencyLabel,
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.BowlingStats = api;
})(typeof window !== 'undefined' ? window : globalThis);
