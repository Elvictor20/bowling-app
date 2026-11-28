/*
 * Componente Alpine de la pestaña Estadísticas de una sala. Vive dentro de roomDetail(), así que
 * usa sus datos (games, members, currentUserId, roomName, activeTab) y su colorFor(). Los cálculos
 * están en stats.js (BowlingStats); aquí solo se pintan.
 */
const CHART_GRID = '#1f2937';
const CHART_TICKS = '#9ca3af';
// Las gráficas viven fuera de los datos de Alpine: si Alpine las envuelve en proxies, Chart.js falla
const CHARTS = {};
const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

function fmtDate(iso) {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`;
}
function fmtNight(key) {
  const [y, m, d] = key.split('-').map(Number);
  const days = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
  return `${days[new Date(y, m - 1, d).getDay()]} ${d} de ${MONTHS[m - 1]} de ${y}`;
}
function fmtMonth(key) {
  const [y, m] = key.split('-').map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}
const signed = v => (v > 0 ? '+' : '') + String(v).replace('.', ',');
const dec = v => (v === null || v === undefined ? '–' : String(v).replace('.', ','));

// Línea discontinua horizontal con etiqueta (200 puntos, media de la sala)
const refLinesPlugin = {
  id: 'refLines',
  afterDatasetsDraw(chart, args, opts) {
    const { ctx, chartArea, scales: { y } } = chart;
    if (!ctx || !chartArea || !y) return;
    (opts.lines || []).forEach(l => {
      if (l.value === null || l.value < y.min || l.value > y.max) return;
      const py = y.getPixelForValue(l.value);
      ctx.save();
      ctx.strokeStyle = l.color; ctx.setLineDash([5, 4]); ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(chartArea.left, py); ctx.lineTo(chartArea.right, py); ctx.stroke();
      ctx.setLineDash([]); ctx.font = '600 10px system-ui, sans-serif'; ctx.textAlign = 'right';
      const tw = ctx.measureText(l.label).width;
      ctx.fillStyle = '#1c1e26e6'; ctx.fillRect(chartArea.right - tw - 6, py - 15, tw + 6, 13);
      ctx.fillStyle = l.color; ctx.fillText(l.label, chartArea.right - 3, py - 5);
      ctx.restore();
    });
  },
};

function roomStats() {
  return {
    statsTab: 'resumen',
    statsTabs: [
      { id: 'resumen', label: 'Resumen' }, { id: 'evolucion', label: 'Evolución' },
      { id: 'jugadores', label: 'Jugadores' }, { id: 'noches', label: 'Noches' },
    ],
    period: 'all',
    periods: [
      { id: 'all', label: 'Todo' }, { id: 'last10', label: 'Últimas 10' },
      { id: 'last5', label: 'Últimas 5' }, { id: 'month', label: 'Este mes' },
    ],
    hidden: [],
    soloYo: false,
    mode: 'points',
    selectedGame: null,
    cardUser: null,
    h2hA: null,
    h2hB: null,
    calMonth: null,
    selectedNight: null,
    share: { open: false, url: '', file: null, canShare: false, title: '' },
    redrawQueued: false,

    initStats() {
      // Varios cambios seguidos (p. ej. «Solo yo» + «Tendencia») se pintan una sola vez
      const redraw = () => {
        if (this.redrawQueued) return;
        this.redrawQueued = true;
        this.$nextTick(() => requestAnimationFrame(() => { this.redrawQueued = false; this.drawCharts(); }));
      };
      ['activeTab', 'statsTab', 'period', 'hidden', 'soloYo', 'mode', 'cardUser', 'games', 'members']
        .forEach(k => this.$watch(k, redraw));
      this.$watch('period', () => { this.selectedGame = null; this.calMonth = null; });
    },

    // ---------- datos ----------
    get fgames() { return BowlingStats.filterGames(this.games || [], this.period); },
    get playedMembers() {
      const ids = new Set(this.fgames.flatMap(g => g.scores.map(s => s.user_id)));
      return (this.members || []).filter(m => ids.has(m.user_id)).sort((a, b) => a.user_id - b.user_id);
    },
    get records() { return BowlingStats.records(this.fgames, this.members || []); },
    get strikeKing() { return BowlingStats.strikeKing(this.fgames, this.members || []); },
    get mostFit() { return BowlingStats.mostFit(this.fgames, this.members || []); },
    get streaks() {
      return BowlingStats.streaks(this.fgames, this.members || [])
        .sort((a, b) => b.onFire - a.onFire || b.currentWins - a.currentWins || b.aboveAvg - a.aboveAvg);
    },
    get nights() { return BowlingStats.nights(this.fgames, this.members || []); },
    get card() {
      const uid = this.cardUserId();
      return uid ? BowlingStats.playerCard(this.fgames, uid) : { games: 0 };
    },
    get h2h() {
      const [a, b] = this.h2hIds();
      return a && b && a !== b ? BowlingStats.headToHead(this.fgames, a, b) : null;
    },
    get marks() { return BowlingStats.marksPerGame(this.fgames, this.members || []); },

    cardUserId() {
      const ids = this.playedMembers.map(m => m.user_id);
      if (this.cardUser && ids.includes(+this.cardUser)) return +this.cardUser;
      return ids.includes(this.currentUserId) ? this.currentUserId : ids[0];
    },
    h2hIds() {
      const ids = this.playedMembers.map(m => m.user_id);
      const a = this.h2hA && ids.includes(+this.h2hA) ? +this.h2hA : (ids.includes(this.currentUserId) ? this.currentUserId : ids[0]);
      const b = this.h2hB && ids.includes(+this.h2hB) ? +this.h2hB : ids.find(id => id !== a);
      return [a, b];
    },
    nameOf(uid) { const m = (this.members || []).find(x => x.user_id === uid); return m ? m.user.full_name : ''; },
    isVisible(uid) {
      if (this.soloYo) return uid === this.currentUserId;
      return !this.hidden.includes(uid);
    },
    togglePlayer(uid) {
      this.soloYo = false;
      this.hidden = this.hidden.includes(uid) ? this.hidden.filter(x => x !== uid) : [...this.hidden, uid];
    },
    fmtDate, fmtNight, fmtMonth, signed, dec,

    // ---------- calendario ----------
    get calMonths() { return [...new Set(this.nights.map(n => n.key.slice(0, 7)))].sort(); },
    currentCalMonth() {
      const ms = this.calMonths;
      return this.calMonth && ms.includes(this.calMonth) ? this.calMonth : ms[ms.length - 1];
    },
    moveCal(step) {
      const ms = this.calMonths, i = ms.indexOf(this.currentCalMonth()) + step;
      if (i >= 0 && i < ms.length) this.calMonth = ms[i];
    },
    calCells() {
      const key = this.currentCalMonth();
      if (!key) return [];
      const [y, m] = key.split('-').map(Number);
      const first = (new Date(y, m - 1, 1).getDay() + 6) % 7;   // lunes = 0
      const days = new Date(y, m, 0).getDate();
      const byDay = Object.fromEntries(this.nights.filter(n => n.key.startsWith(key)).map(n => [+n.key.slice(8), n]));
      const cells = Array.from({ length: first }, (_, i) => ({ id: 'e' + i, day: null }));
      for (let d = 1; d <= days; d++) cells.push({ id: 'd' + d, day: d, night: byDay[d] || null });
      return cells;
    },
    pickNight(n) {
      this.selectedNight = n.key;
      this.$nextTick(() => document.getElementById('night-' + n.key)?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
    },

    // ---------- gráficas ----------
    destroyChart(id) { if (CHARTS[id]) { CHARTS[id].destroy(); delete CHARTS[id]; } },
    makeChart(id, config) {
      this.destroyChart(id);
      const el = document.getElementById(id);
      if (!el || !el.offsetParent) return;
      CHARTS[id] = new Chart(el.getContext('2d'), config);
    },
    baseOptions(extra = {}) {
      return {
        responsive: true, maintainAspectRatio: false, animation: { duration: 300 },
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: { display: false },
          tooltip: { backgroundColor: '#111827', borderColor: '#374151', borderWidth: 1, padding: 10, cornerRadius: 8 },
        },
        scales: {
          x: { grid: { color: CHART_GRID }, ticks: { color: CHART_TICKS, maxRotation: 0, autoSkipPadding: 12, font: { size: 10 } } },
          y: { grid: { color: CHART_GRID }, ticks: { color: CHART_TICKS, font: { size: 10 } } },
        },
        ...extra,
      };
    },
    lineDataset(uid, data, extra = {}) {
      const c = this.colorFor(uid), on = this.isVisible(uid);
      const dim = this.soloYo && !on;
      return {
        _uid: uid, label: this.nameOf(uid), data, borderColor: dim ? c + '33' : c, backgroundColor: c,
        borderWidth: on ? 2.5 : 1, pointRadius: on ? 3 : 0, pointHoverRadius: 5, tension: 0.3, spanGaps: true,
        hidden: !on && !this.soloYo, ...extra,
      };
    },

    drawCharts() {
      if (this.activeTab !== 'stats') return;
      Object.keys(CHARTS).forEach(id => this.destroyChart(id));
      if (!this.fgames.length) return;
      if (this.statsTab === 'evolucion') { this.drawEvolution(); this.drawRace(); this.drawWins(); this.drawMonths(); }
      if (this.statsTab === 'jugadores') { this.drawDistribution(); this.drawMarks(); }
    },

    drawEvolution() {
      const games = this.fgames, s = BowlingStats.series(games, this.members, this.mode);
      const all = games.flatMap(g => g.scores.map(x => x.score));
      const roomAvg = BowlingStats.round1(BowlingStats.mean(all));
      const rec = this.records.highest;
      const datasets = this.playedMembers.map(m => {
        const data = s.data[m.user_id];
        // Estrella en el récord del periodo (solo en modo puntos)
        const star = data.map((v, i) => this.mode === 'points' && rec && m.user_id === rec.user_id && v === rec.value
          && games[i].played_at === rec.date);
        return this.lineDataset(m.user_id, data, {
          pointStyle: star.map(x => (x ? 'star' : 'circle')),
          pointRadius: star.map(x => (x ? 9 : (this.isVisible(m.user_id) ? 3 : 0))),
          pointBorderWidth: star.map(x => (x ? 2 : 1)),
        });
      });
      const max = Math.max(...all), min = Math.min(...all);
      this.makeChart('evoChart', {
        type: 'line', data: { labels: s.labels, datasets }, plugins: [refLinesPlugin],
        options: this.baseOptions({
          onClick: (e, els) => {
            if (!els.length) return;
            const i = els[0].index, g = games[i];
            this.selectedGame = { label: s.labels[i], date: g.played_at, ranking: BowlingStats.gameRanking(g) };
          },
          plugins: {
            ...this.baseOptions().plugins,
            refLines: { lines: [
              { value: 200, label: '200', color: '#f59e0b99' },
              { value: roomAvg, label: 'Media sala ' + dec(roomAvg), color: '#9ca3afaa' },
            ] },
            tooltip: { ...this.baseOptions().plugins.tooltip, itemSort: (a, b) => b.parsed.y - a.parsed.y,
              filter: i => i.parsed.y !== null && (!this.soloYo || i.dataset._uid === this.currentUserId) },
          },
          scales: {
            ...this.baseOptions().scales,
            y: { ...this.baseOptions().scales.y, min: Math.max(0, Math.floor((min - 15) / 50) * 50), max: max > 250 ? 300 : Math.ceil((max + 15) / 50) * 50 },
          },
        }),
      });
    },

    drawRace() {
      const games = this.fgames, race = BowlingStats.rankingRace(games, this.members);
      const n = this.playedMembers.length;
      this.makeChart('raceChart', {
        type: 'line',
        data: { labels: games.map((g, i) => 'P' + (i + 1)),
                datasets: this.playedMembers.map(m => this.lineDataset(m.user_id, race[m.user_id], { stepped: false, tension: 0.25 })) },
        options: this.baseOptions({
          scales: {
            ...this.baseOptions().scales,
            y: { ...this.baseOptions().scales.y, reverse: true, min: 1, max: Math.max(n, 2),
                 ticks: { ...this.baseOptions().scales.y.ticks, stepSize: 1, callback: v => '#' + v } },
          },
          plugins: { ...this.baseOptions().plugins, tooltip: { ...this.baseOptions().plugins.tooltip,
            itemSort: (a, b) => a.parsed.y - b.parsed.y, callbacks: { label: c => ` #${c.parsed.y} ${c.dataset.label}` } } },
        }),
      });
    },

    drawWins() {
      const games = this.fgames, wins = BowlingStats.cumulativeWins(games, this.members);
      this.makeChart('winsChart', {
        type: 'line',
        data: { labels: games.map((g, i) => 'P' + (i + 1)),
                datasets: this.playedMembers.map(m => this.lineDataset(m.user_id, wins[m.user_id], { stepped: true, tension: 0, pointRadius: 0 })) },
        options: this.baseOptions({
          scales: { ...this.baseOptions().scales, y: { ...this.baseOptions().scales.y, beginAtZero: true, ticks: { ...this.baseOptions().scales.y.ticks, precision: 0 } } },
          plugins: { ...this.baseOptions().plugins, tooltip: { ...this.baseOptions().plugins.tooltip, itemSort: (a, b) => b.parsed.y - a.parsed.y } },
        }),
      });
    },

    drawMonths() {
      const m = BowlingStats.monthlyAverages(this.fgames, this.members);
      this.makeChart('monthChart', {
        type: 'bar',
        data: { labels: m.months.map(fmtMonth),
                datasets: this.playedMembers.filter(p => this.isVisible(p.user_id)).map(p => ({
                  label: this.nameOf(p.user_id), data: m.data[p.user_id], backgroundColor: this.colorFor(p.user_id), borderRadius: 4, maxBarThickness: 18,
                })) },
        options: this.baseOptions({ scales: { ...this.baseOptions().scales, y: { ...this.baseOptions().scales.y, beginAtZero: true } } }),
      });
    },

    drawDistribution() {
      const uid = this.cardUserId();
      if (!uid || !this.card.games) return;
      const d = BowlingStats.distribution(this.card.scores);
      this.makeChart('distChart', {
        type: 'bar',
        data: { labels: d.map(b => `${b.lo}-${b.hi}`),
                datasets: [{ label: 'Partidas', data: d.map(b => b.count), backgroundColor: this.colorFor(uid), borderRadius: 4 }] },
        options: this.baseOptions({ scales: { ...this.baseOptions().scales, y: { ...this.baseOptions().scales.y, beginAtZero: true, ticks: { ...this.baseOptions().scales.y.ticks, precision: 0 } } } }),
      });
    },

    drawMarks() {
      const rows = this.marks;
      this.makeChart('marksChart', {
        type: 'bar',
        data: { labels: rows.map(r => r.name),
                datasets: [
                  { label: '🎳 Plenos por partida', data: rows.map(r => r.strikes), backgroundColor: rows.map(r => this.colorFor(r.id)), borderRadius: 4 },
                  { label: '🔲 Semiplenos por partida', data: rows.map(r => r.spares), backgroundColor: rows.map(r => this.colorFor(r.id) + '66'), borderRadius: 4 },
                ] },
        options: this.baseOptions({
          indexAxis: 'y',
          plugins: { ...this.baseOptions().plugins, legend: { display: true, labels: { color: CHART_TICKS, boxWidth: 10, font: { size: 11 } } } },
          scales: { x: { ...this.baseOptions().scales.x, beginAtZero: true }, y: { ...this.baseOptions().scales.y, grid: { display: false } } },
        }),
      });
    },

    // ---------- compartir la noche ----------
    async shareNight(n) {
      const canvas = drawNightImage(n, this.roomName, uid => this.colorFor(uid));
      const blob = await new Promise(r => canvas.toBlob(r, 'image/png'));
      const file = new File([blob], `bolos-${n.key}.png`, { type: 'image/png' });
      if (this.share.url) URL.revokeObjectURL(this.share.url);
      this.share = {
        open: true, url: URL.createObjectURL(blob), file, title: fmtNight(n.key),
        canShare: !!(navigator.canShare && navigator.canShare({ files: [file] })),
      };
    },
    async sendShare() {
      try {
        await navigator.share({ files: [this.share.file], title: 'Noche de bolos', text: `Resumen de la noche · ${this.share.title}` });
      } catch (e) { /* el usuario ha cancelado */ }
    },
  };
}

// Imagen 1080×1350 (formato vertical de WhatsApp e Instagram) con el resumen de una noche
function drawNightImage(night, roomName, colorFor) {
  const W = 1080, H = 1350, c = document.createElement('canvas');
  c.width = W; c.height = H;
  const x = c.getContext('2d');
  const font = (w, s) => `${w} ${s}px system-ui, -apple-system, "Segoe UI", sans-serif`;
  const grad = x.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, '#1e1b4b'); grad.addColorStop(1, '#0b0c10');
  x.fillStyle = grad; x.fillRect(0, 0, W, H);

  x.fillStyle = '#a78bfa'; x.font = font(800, 44); x.fillText('🎳 BowlingClub', 72, 110);
  x.fillStyle = '#9ca3af'; x.font = font(500, 34); x.fillText(roomName || '', 72, 165);
  x.fillStyle = '#f3f4f6'; x.font = font(800, 56); x.fillText('Noche de bolos', 72, 270);
  x.fillStyle = '#d1d5db'; x.font = font(500, 36);
  x.fillText(`${fmtNight(night.key)} · ${night.games} ${night.games === 1 ? 'partida' : 'partidas'}`, 72, 325);

  const w = night.winner || night.ranking[0];
  if (w) {
    x.fillStyle = '#ffffff12'; roundRect(x, 72, 380, W - 144, 250, 36); x.fill();
    x.fillStyle = '#ffffff'; x.font = font(400, 110); x.fillText('👑', 110, 545);
    x.fillStyle = '#fbbf24'; x.font = font(700, 32); x.fillText(night.winner ? 'GANADOR DE LA NOCHE' : 'JUGADOR DE LA NOCHE', 270, 455);
    x.fillStyle = '#ffffff'; x.font = font(900, 76); x.fillText(clip(x, w.name, 620), 270, 540);
    x.fillStyle = '#d1d5db'; x.font = font(500, 32);
    x.fillText(`${dec(w.avgValue)} de puntuación · ${w.wins} ${w.wins === 1 ? 'victoria' : 'victorias'} · mejor ${w.best}`, 270, 595);
  }

  let y = 720;
  x.fillStyle = '#9ca3af'; x.font = font(700, 28); x.fillText('CLASIFICACIÓN', 72, y - 30);
  night.ranking.slice(0, 6).forEach(r => {
    x.fillStyle = '#ffffff0d'; roundRect(x, 72, y, W - 144, 88, 22); x.fill();
    x.fillStyle = ['#fbbf24', '#d1d5db', '#d97706'][r.rank - 1] || '#6b7280'; x.font = font(800, 38); x.fillText('#' + r.rank, 100, y + 58);
    x.fillStyle = colorFor(r.user_id); x.beginPath(); x.arc(225, y + 44, 26, 0, Math.PI * 2); x.fill();
    x.fillStyle = '#0b0c10'; x.font = font(800, 28); x.textAlign = 'center'; x.fillText(r.name.charAt(0).toUpperCase(), 225, y + 54); x.textAlign = 'left';
    x.fillStyle = '#f3f4f6'; x.font = font(700, 36); x.fillText(clip(x, r.name, 280), 275, y + 57);
    x.fillStyle = '#9ca3af'; x.font = font(500, 26); x.fillText(`🎳 ${r.strikes}  🔲 ${r.spares}  🏆 ${r.wins}`, 575, y + 55);
    x.fillStyle = '#c4b5fd'; x.font = font(800, 38); x.textAlign = 'right'; x.fillText(dec(r.avgValue), W - 100, y + 58); x.textAlign = 'left';
    y += 104;
  });
  x.fillStyle = '#6b7280'; x.font = font(500, 26);
  x.fillText('Puntuación = (puntos + 5 por semipleno + 10 por pleno) ÷ partidas', 72, H - 60);
  return c;
}
function roundRect(x, l, t, w, h, r) {
  x.beginPath(); x.moveTo(l + r, t); x.arcTo(l + w, t, l + w, t + h, r); x.arcTo(l + w, t + h, l, t + h, r);
  x.arcTo(l, t + h, l, t, r); x.arcTo(l, t, l + w, t, r); x.closePath();
}
function clip(x, text, max) {
  if (x.measureText(text).width <= max) return text;
  while (text.length > 1 && x.measureText(text + '…').width > max) text = text.slice(0, -1);
  return text + '…';
}
