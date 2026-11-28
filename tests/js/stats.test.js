// Tests de app/static/js/stats.js. Ejecutar con: node --test tests/js/
const test = require('node:test');
const assert = require('node:assert/strict');
const S = require('../../app/static/js/stats.js');

const members = [
  { user_id: 1, user: { full_name: 'Ana' } },
  { user_id: 2, user: { full_name: 'Bea' } },
  { user_id: 3, user: { full_name: 'Carlos' } },
];
let nextId = 1;
// sc: [user_id, score, strikes, spares]
const game = (played_at, ...sc) => ({
  id: nextId++, played_at,
  scores: sc.map(([user_id, score, strikes = 0, spares = 0]) => ({ user_id, score, strikes, spares })),
});

const G = [
  game('2026-10-01T20:00:00', [1, 150, 2, 3], [2, 120, 1, 2]),
  game('2026-10-01T21:00:00', [1, 170, 3, 3], [2, 180, 4, 2], [3, 100, 0, 1]),
  game('2026-10-02T00:30:00', [2, 200, 5, 3], [3, 140, 1, 4]),          // misma noche que el 1/10
  game('2026-11-05T20:00:00', [1, 190, 4, 3], [2, 130, 1, 3]),
  game('2026-11-12T20:00:00', [1, 210, 6, 2]),                           // en solitario: no cuenta como victoria
  game('2026-11-19T20:00:00', [1, 220, 6, 3], [3, 150, 2, 3]),
];

test('value usa la misma fórmula que el servidor', () => {
  assert.equal(S.value({ score: 150, strikes: 2, spares: 3 }), 150 + 15 + 20);
});

test('filterGames ordena y recorta por periodo', () => {
  const shuffled = [G[3], G[0], G[5], G[1], G[2], G[4]];
  assert.deepEqual(S.filterGames(shuffled, 'all').map(g => g.id), G.map(g => g.id));
  assert.deepEqual(S.filterGames(shuffled, 'last5').map(g => g.id), G.slice(1).map(g => g.id));
  assert.equal(S.filterGames(G, 'month', new Date('2026-11-20T12:00:00')).length, 3);
});

test('gameRanking reparte puestos y comparte empates', () => {
  const g = game('2026-10-01T20:00:00', [1, 100, 0, 0], [2, 90, 1, 0], [3, 80, 0, 0]);
  assert.deepEqual(S.gameRanking(g).map(s => [s.user_id, s.rank]), [[1, 1], [2, 1], [3, 3]]);
});

test('winnersOf ignora las partidas en solitario', () => {
  assert.deepEqual(S.winnersOf(G[4]), []);
  assert.deepEqual(S.winnersOf(G[1]), [2]);
});

test('rollingAvg salta las ausencias', () => {
  assert.deepEqual(S.rollingAvg([100, null, 200, 300, 400]), [100, null, 150, 200, 300]);
});

test('series da null cuando alguien no juega', () => {
  const s = S.series(G, members);
  assert.equal(s.labels.length, 6);
  assert.deepEqual(s.data[3], [null, 100, 140, null, null, 150]);
  assert.equal(s.labels[0], 'P1 · 01/10');
});

test('rankingRace sigue la puntuación acumulada', () => {
  const r = S.rankingRace(G, members);
  // Tras la 2.ª partida: Ana (185+215)/2 = 200, Bea (140+230)/2 = 185, Carlos 105
  assert.deepEqual(r[1].slice(0, 2), [1, 1]);
  assert.deepEqual(r[2].slice(0, 3), [2, 2, 1]);
  assert.deepEqual(r[3][0], null);
  assert.equal(r[1][5], 1);
});

test('cumulativeWins suma victorias sin contar partidas en solitario', () => {
  const w = S.cumulativeWins(G, members);
  assert.deepEqual(w[1], [1, 1, 1, 2, 2, 3]);
  assert.deepEqual(w[2], [0, 1, 2, 2, 2, 2]);
});

test('distribution agrupa en tramos y recorta los extremos vacíos', () => {
  const d = S.distribution([100, 105, 150, 299, 300]);
  assert.equal(d[0].lo, 100);
  assert.equal(d[d.length - 1].hi, 300);
  assert.equal(d[0].count, 2);
  assert.equal(d[d.length - 1].count, 2);
});

test('monthlyAverages calcula la media de puntos por mes', () => {
  const m = S.monthlyAverages(G, members);
  assert.deepEqual(m.months, ['2026-10', '2026-11']);
  assert.deepEqual(m.data[1], [160, 206.7]);
  assert.deepEqual(m.data[3], [120, 150]);
});

test('playerCard resume a un jugador', () => {
  const c = S.playerCard(G, 1);
  assert.equal(c.games, 5);
  assert.equal(c.avgPoints, 188);
  assert.equal(c.best.score, 220);
  assert.equal(c.worst.score, 150);
  assert.equal(c.wins, 3);
  assert.equal(c.winPct, 75);                 // 3 de 4 partidas con rivales
  assert.equal(c.trend, round(((190 + 210 + 220) / 3) - 188));
  assert.deepEqual(c.last5, [150, 170, 190, 210, 220]);
  assert.equal(S.playerCard(G, 99).games, 0);
});
const round = x => Math.round(x * 10) / 10;

test('headToHead compara solo las partidas jugadas juntos', () => {
  const h = S.headToHead(G, 1, 2);
  assert.equal(h.games, 3);
  assert.deepEqual([h.winsA, h.winsB, h.ties], [2, 1, 0]);
  assert.equal(h.recent[0].a, 190);           // la más reciente primero
});

test('records encuentra récords y la mayor mejora mensual', () => {
  const r = S.records(G, members);
  assert.equal(r.highest.value, 220);
  assert.equal(r.lowest.value, 100);
  assert.equal(r.mostStrikes.value, 6);
  assert.equal(r.mostGames.name, 'Ana');
  assert.equal(r.improvement.name, 'Ana');
  assert.equal(r.improvement.value, round(206.7 - 160));
});

test('mostFit compara las últimas 3 con la media propia y pide 4 partidas', () => {
  const f = S.mostFit(G, members);
  assert.equal(f.name, 'Ana');
  assert.ok(f.value > 0);
  assert.equal(S.mostFit(G.slice(0, 3), members), null);
});

test('streaks cuenta victorias seguidas y partidas sobre la media', () => {
  const s = Object.fromEntries(S.streaks(G, members).map(r => [r.user_id, r]));
  assert.equal(s[1].currentWins, 2);          // ganó las 2 últimas con rivales
  assert.equal(s[1].bestWins, 2);
  assert.equal(s[1].aboveAvg, 3);
  assert.equal(s[1].onFire, true);
});

test('nights agrupa por noche (hasta las 6:00) y elige ganador', () => {
  const n = S.nights(G, members);
  assert.equal(n.length, 4);
  const first = n[n.length - 1];
  assert.equal(first.key, '2026-10-01');
  assert.equal(first.games, 3);
  assert.equal(first.winner.name, 'Bea');
  assert.equal(n.find(x => x.key === '2026-11-12').winner, null);   // noche en solitario
});
