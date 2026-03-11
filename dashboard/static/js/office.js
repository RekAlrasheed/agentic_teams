/* ═══════════════════════════════════════════════════════════════
   NAVAIA CREW HQ — Pixel Office v8
   Modern white furniture, Navaia logo, zone-based idle behavior
   ═══════════════════════════════════════════════════════════════ */

const canvas = document.getElementById('office-canvas');
const ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

const TILE = 16, Z = 3, T = TILE * Z;
const COLS = 21, ROWS = 21;
canvas.width = COLS * T; canvas.height = ROWS * T;
const CW = canvas.width, CH = canvas.height;

/* ── Asset paths ───────────────────────────────────────────── */
const PA = '/static/sprites/pixel-agents/';
const IMG = {};
let TILES = [], FURN_LIST = [], CATALOG = {};
let assetsReady = false, loadCount = 0, loadTotal = 0;

function loadImg(key, src) {
  loadTotal++;
  return new Promise(res => {
    const img = new Image();
    img.onload = () => { IMG[key] = img; loadCount++; res(); };
    img.onerror = () => { console.warn('Skip:', key); loadCount++; res(); };
    img.src = src;
  });
}

async function loadAssets() {
  const loads = [];
  // Core
  loads.push(loadImg('floors', PA + 'floors.png'));
  loads.push(loadImg('walls', PA + 'walls.png'));
  for (let i = 0; i < 6; i++) loads.push(loadImg('char_' + i, PA + 'characters/char_' + i + '.png'));

  // Layout + catalog JSONs
  const [layoutJ, catalogJ] = await Promise.all([
    fetch(PA + 'default-layout.json').then(r => r.json()),
    fetch(PA + 'furniture/furniture-catalog.json').then(r => r.json()),
  ]);
  TILES = layoutJ.tiles;
  FURN_LIST = layoutJ.furniture;
  for (const a of catalogJ.assets) CATALOG[a.id] = a;

  // Furniture images (deduplicated)
  const seen = new Set();
  for (const item of FURN_LIST) {
    const m = CATALOG[item.type];
    if (m && m.file && !seen.has(item.type)) {
      seen.add(item.type);
      loads.push(loadImg('f_' + item.type, PA + m.file));
    }
  }
  await Promise.all(loads);
}

/* ── Furniture Modernization ─────────────────────────────── */
const FURNITURE_MODERNIZE = {
  'ASSET_NEW_106': 'ASSET_15',   // TABLE_WOOD → COUNTER_PLASTIC_SM (48x32, 3x2)
  'ASSET_49':      'ASSET_35',   // STOOL → CHAIR_ROTATING_FRONT (16x16, 1x1)
  'ASSET_17':      'ASSET_23',   // WOODEN_BOOKSHELF_SMALL → WHITE_BOOKSHELF_1 (32x32, 2x2)
  'ASSET_18':      'ASSET_24',   // FULL_WOODEN_BOOKSHELF → FULL_WHITE_BOOKSHELF_1 (32x32, 2x2)
};

async function modernizeFurniture() {
  // Swap old furniture types for modern white equivalents
  for (const item of FURN_LIST) {
    if (FURNITURE_MODERNIZE[item.type]) {
      item.type = FURNITURE_MODERNIZE[item.type];
    }
  }

  // Remove meeting room painting (ASSET_102 at col 5, row 0)
  for (let i = FURN_LIST.length - 1; i >= 0; i--) {
    if (FURN_LIST[i].type === 'ASSET_102' && FURN_LIST[i].col === 5 && FURN_LIST[i].row === 0) {
      FURN_LIST.splice(i, 1);
    }
  }

  // Inject kitchen appliances
  FURN_LIST.push({ type: 'ASSET_55', col: 15, row: 10 });  // COFFEE_MACHINE
  FURN_LIST.push({ type: 'ASSET_151', col: 16, row: 10 }); // MICROWAVE

  // Load images for any new/swapped furniture types
  const loads = [];
  const seen = new Set();
  for (const item of FURN_LIST) {
    const m = CATALOG[item.type];
    if (m && m.file && !IMG['f_' + item.type] && !seen.has(item.type)) {
      seen.add(item.type);
      loads.push(loadImg('f_' + item.type, PA + m.file));
    }
  }
  if (loads.length) await Promise.all(loads);
}

/* ── Agent config ──────────────────────────────────────────── */
const AGENT_CFG = {
  pm:        { sprite:'char_0', name:'Navi',  color:'#4a9eff', sCol:3, sRow:16, dCol:3, dRow:14 },
  creative:  { sprite:'char_1', name:'Muse',  color:'#ff8c42', sCol:8, sRow:16, dCol:8, dRow:14 },
  technical: { sprite:'char_2', name:'Arch',  color:'#a855f7', sCol:3, sRow:20, dCol:3, dRow:18 },
  admin:     { sprite:'char_3', name:'Sage',  color:'#22c55e', sCol:8, sRow:20, dCol:8, dRow:18 },
};

/* ── Tile helpers ───────────────────────────────────────────── */
function tileAt(c, r) {
  if (c < 0 || c >= COLS || r < 0 || r >= ROWS) return 8;
  return TILES[r * COLS + c];
}
function isFloor(c, r) { const t = tileAt(c, r); return t !== 0 && t !== 8; }

/* ── Tile rendering ────────────────────────────────────────── */
function drawTiles() {
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const t = tileAt(c, r), x = c * T, y = r * T;
      if (t === 8) {
        ctx.fillStyle = '#1a1714'; ctx.fillRect(x, y, T, T);
      } else if (t === 0) {
        // Wall top
        ctx.fillStyle = '#3D3833'; ctx.fillRect(x, y, T, T);
        ctx.fillStyle = (c + r) % 2 ? '#44403A' : '#3A3630';
        ctx.fillRect(x + Z, y + Z, T - 2 * Z, T - 2 * Z);
      } else {
        // Floor from floors.png
        if (IMG.floors) {
          ctx.drawImage(IMG.floors, t * 16, 0, 16, 16, x, y, T, T);
        } else {
          ctx.fillStyle = t === 2 ? '#8B7355' : t === 6 ? '#9B8B6B' : '#7B6B55';
          ctx.fillRect(x, y, T, T);
        }
      }
    }
  }
}

/* ── Wall faces (depth) ────────────────────────────────────── */
function wallFaceObjs() {
  const d = [];
  const FH = 8 * Z;
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      if (tileAt(c, r) !== 0) continue;
      if (!isFloor(c, r + 1)) continue;
      const x = c * T, y = r * T;
      d.push({ zY: r * T + T, draw() {
        ctx.fillStyle = '#2D2823'; ctx.fillRect(x, y + T, T, FH);
        ctx.fillStyle = '#1D1813'; ctx.fillRect(x, y + T + FH - Z, T, Z);
        ctx.fillStyle = '#3D3833'; ctx.fillRect(x, y + T, Z, FH);
        ctx.fillStyle = '#252018'; ctx.fillRect(x + T - Z, y + T, Z, FH);
      }});
    }
  }
  return d;
}

/* ── Furniture rendering ───────────────────────────────────── */
function furnObjs() {
  const d = [];
  for (const item of FURN_LIST) {
    const meta = CATALOG[item.type];
    const img = IMG['f_' + item.type];
    if (!meta || !img) continue;
    const px = item.col * T, py = item.row * T;
    const w = img.width * Z, h = img.height * Z;
    const zy = (item.row + (meta.footprintH || 1)) * T;
    d.push({ zY: zy, draw() { ctx.drawImage(img, px, py, w, h); } });
  }
  return d;
}

/* ── Character rendering ───────────────────────────────────── */
// Sprite sheets: 112×96 = 7 frames (16px) × 3 rows (32px)
// Row 0: down, Row 1: right, Row 2: up. Left = flip right.
const DIR_ROW = { down: 0, right: 1, up: 2, left: 1 };

function charObjs() {
  const d = [];
  for (const a of agentData) {
    const cfg = AGENT_CFG[a.id]; if (!cfg) continue;
    const sheet = IMG[cfg.sprite]; if (!sheet) continue;
    const s = getSim(a.id), as = a.state || 'OFFLINE';
    const sitting = s.st === 'sit' || s.st === 'idle_sit', walking = s.st === 'walk';

    let dir = s.dir, fi = 0;
    if (s.st === 'idle_sit') {
      dir = s._sitDir || 'down'; fi = Math.floor(frame / 30) % 2;
    } else if (sitting && (as === 'WORKING' || as === 'STARTING')) {
      dir = 'up'; fi = (Math.floor(frame / 12) % 2) + 1;
    } else if (walking) {
      fi = s.wf % 7;
    } else if (as === 'DONE') {
      fi = (Math.floor(frame / 8) % 3);
    }

    const row = DIR_ROW[dir];
    const sx = fi * 16, sy = row * 32;
    const flip = dir === 'left';
    const sprW = 16 * Z, sprH = 32 * Z;
    const dx = s.x - sprW / 2;
    const sitOff = sitting ? 6 * Z : 0;  // typing offset: push down like Pixel Agents
    const dy = s.y - sprH + sitOff;

    d.push({ zY: s.y, agentId: a.id, draw() {
      ctx.save();
      if (as === 'OFFLINE') ctx.globalAlpha = 0.4;
      if (flip) {
        ctx.translate(dx + sprW, 0);
        ctx.scale(-1, 1);
        ctx.drawImage(sheet, sx, sy, 16, 32, 0, dy, sprW, sprH);
      } else {
        ctx.drawImage(sheet, sx, sy, 16, 32, dx, dy, sprW, sprH);
      }
      ctx.restore();
      // Selection highlight
      if (selectedAgent === a.id) {
        ctx.strokeStyle = cfg.color; ctx.lineWidth = 2;
        ctx.setLineDash([4, 3]);
        ctx.strokeRect(dx - 2, dy - 2, sprW + 4, sprH + 4);
        ctx.setLineDash([]);
      }
    }});
  }
  return d;
}

/* ── Overlays ──────────────────────────────────────────────── */
function drawOverlays() {
  for (const a of agentData) {
    const cfg = AGENT_CFG[a.id]; if (!cfg) continue;
    const s = getSim(a.id), as = a.state || 'OFFLINE';
    const cx = s.x, by = s.y + 12 * Z;

    ctx.textAlign = 'center';
    ctx.font = '8px "Press Start 2P"'; ctx.fillStyle = cfg.color;
    ctx.fillText(cfg.name, cx, by + 4);
    const sc = { WORKING: '#4a9eff', IDLE: '#fbbf24', OFFLINE: '#555', STARTING: '#ff8c42', DONE: '#22c55e' };
    ctx.font = '7px "Press Start 2P"'; ctx.fillStyle = sc[as] || '#555';
    ctx.fillText(as, cx, by + 14);
    ctx.textAlign = 'left';

    // Task bubble
    if ((as === 'WORKING' || as === 'STARTING') && a.current_task && s.st === 'sit') {
      const bx = cx, bby = s.y - 22 * Z;
      const txt = a.current_task.length > 18 ? a.current_task.slice(0, 18) + '..' : a.current_task;
      ctx.font = '7px "Press Start 2P"';
      const tw = Math.max(ctx.measureText(txt).width + 10, 40);
      const rx = bx - tw / 2, ry = bby - 16;
      ctx.fillStyle = '#0a0e16ee'; ctx.fillRect(rx, ry, tw, 16);
      ctx.strokeStyle = cfg.color; ctx.lineWidth = 1.5; ctx.strokeRect(rx, ry, tw, 16);
      ctx.fillStyle = '#0a0e16ee';
      ctx.beginPath(); ctx.moveTo(bx - 3, ry + 16); ctx.lineTo(bx, ry + 20); ctx.lineTo(bx + 3, ry + 16); ctx.fill(); ctx.stroke();
      ctx.fillRect(bx - 2, ry + 15, 4, 2);
      ctx.fillStyle = cfg.color; ctx.textAlign = 'center';
      ctx.fillText(txt, bx, ry + 11); ctx.textAlign = 'left';
    }

    // Chat bubble
    if (s.st === 'chat' && s.ct > 0) {
      const bx = cx, bby = s.y - 20 * Z;
      ctx.font = '7px "Press Start 2P"';
      const tw = Math.max(ctx.measureText(s.cl).width + 8, 32);
      const rx = bx - tw / 2, ry = bby - 14;
      ctx.fillStyle = '#1a1820ee'; ctx.fillRect(rx, ry, tw, 14);
      ctx.strokeStyle = '#fbbf24'; ctx.lineWidth = 1; ctx.strokeRect(rx, ry, tw, 14);
      ctx.fillStyle = '#fbbf24'; ctx.textAlign = 'center';
      ctx.fillText(s.cl, bx, ry + 10); ctx.textAlign = 'left';
    }

    if (as === 'DONE') {
      ctx.font = '8px "Press Start 2P"'; ctx.fillStyle = '#22c55e';
      ctx.textAlign = 'center'; ctx.fillText('DONE!', cx, s.y - 20 * Z); ctx.textAlign = 'left';
    }
    if (as === 'OFFLINE' && frame % 12 < 6) {
      ctx.font = '7px "Press Start 2P"'; ctx.fillStyle = '#556';
      ctx.fillText('z', cx + 8, s.y - 16 * Z);
      ctx.fillText('Z', cx + 14, s.y - 20 * Z);
    }
  }

  // Navaia logo — meeting room wall (row 1, cols 3-8)
  const logoX = 3 * T, logoY = 1 * T;
  const logoW = 5 * T, logoH = T;
  ctx.fillStyle = '#0a0e16dd';
  ctx.fillRect(logoX + 4, logoY + 4, logoW - 8, logoH - 8);
  ctx.strokeStyle = '#4a9eff'; ctx.lineWidth = 2;
  ctx.strokeRect(logoX + 4, logoY + 4, logoW - 8, logoH - 8);
  ctx.font = '14px "Press Start 2P"'; ctx.fillStyle = '#4a9eff';
  ctx.textAlign = 'center';
  ctx.fillText('NAVAIA', logoX + logoW / 2, logoY + logoH / 2 + 5);
  ctx.textAlign = 'left';

  // Branding
  ctx.font = '10px "Press Start 2P"'; ctx.fillStyle = '#4a9eff88';
  ctx.textAlign = 'center';
  ctx.fillText('NAVAIA HQ', COLS * T / 2, 14);
  ctx.textAlign = 'left';

  const el = document.getElementById('office-clock');
  if (el) el.textContent = new Date().toLocaleTimeString();
}

/* ── Pathfinding & Simulation ──────────────────────────────── */
const WALKABLE = new Set();
const BLOCKED = new Set();

function buildNavGrid() {
  WALKABLE.clear(); BLOCKED.clear();
  for (let r = 0; r < ROWS; r++)
    for (let c = 0; c < COLS; c++)
      if (isFloor(c, r)) WALKABLE.add(`${c},${r}`);

  // Block furniture tiles (skip chairs — agents can sit on them)
  for (const item of FURN_LIST) {
    const m = CATALOG[item.type]; if (!m) continue;
    const isChair = (m.file || '').includes('/chairs/');
    if (isChair) continue;
    for (let dr = 0; dr < (m.footprintH || 1); dr++)
      for (let dc = 0; dc < (m.footprintW || 1); dc++)
        BLOCKED.add(`${item.col + dc},${item.row + dr}`);
  }

  // Ensure all agent seat positions are always walkable
  for (const id of Object.keys(AGENT_CFG)) {
    const cfg = AGENT_CFG[id];
    BLOCKED.delete(`${cfg.sCol},${cfg.sRow}`);
  }
}

function canWalk(c, r) { return WALKABLE.has(`${c},${r}`) && !BLOCKED.has(`${c},${r}`); }

function findPath(fc, fr, tc, tr) {
  if (fc === tc && fr === tr) return [];
  if (!canWalk(tc, tr)) return [];
  const vis = new Set([`${fc},${fr}`]);
  const q = [{ c: fc, r: fr, path: [] }];
  while (q.length) {
    const { c, r, path } = q.shift();
    for (const [dc, dr] of [[0, -1], [0, 1], [-1, 0], [1, 0]]) {
      const nc = c + dc, nr = r + dr, k = `${nc},${nr}`;
      if (vis.has(k) || !canWalk(nc, nr)) continue;
      vis.add(k);
      const np = [...path, { c: nc, r: nr }];
      if (nc === tc && nr === tr) return np;
      q.push({ c: nc, r: nr, path: np });
    }
  }
  return [];
}

// Weighted zone system for idle behavior
const ZONES = {
  lounge: {
    weight: 0.45,
    chatChance: 0.08,
    pois: [
      { c: 14, r: 18, sit: 'left' },   // lounge chair
      { c: 17, r: 18, sit: 'right' },  // lounge chair
      { c: 15, r: 19 },                // coffee table area
      { c: 16, r: 19 },                // coffee table area
      { c: 14, r: 20 },                // lounge area
      { c: 17, r: 20 },                // lounge area
    ],
    chats: ['nice chair!', 'break time', 'so comfy', "how's work?"],
  },
  kitchen: {
    weight: 0.35,
    chatChance: 0.08,
    pois: [
      { c: 14, r: 12 },  // vending machine area
      { c: 16, r: 12 },  // counter area
      { c: 15, r: 12 },  // near coffee machine
      { c: 18, r: 12 },  // counter area
      { c: 15, r: 13 },  // kitchen center
      { c: 18, r: 13 },  // kitchen floor
    ],
    chats: ['coffee?', 'mmm snacks', 'hungry!', 'need caffeine'],
  },
  meeting: {
    weight: 0.05,
    chatChance: 0.015,
    pois: [
      { c: 6, r: 4 },
      { c: 5, r: 6 },
    ],
    chats: ['meeting?', 'PR review?', 'deadline?', 'great idea'],
  },
  office: {
    weight: 0.15,
    chatChance: 0.015,
    pois: [
      { c: 5, r: 9 },   // corridor
      { c: 6, r: 9 },   // corridor
      { c: 6, r: 12 },  // office floor
      { c: 7, r: 13 },  // office floor
    ],
    chats: ['nice work!', 'on it!', 'bug found', 'deploying..'],
  },
};

function pickZonePOI() {
  const r = Math.random();
  let cum = 0;
  for (const [name, zone] of Object.entries(ZONES)) {
    cum += zone.weight;
    if (r <= cum) {
      const poi = zone.pois[Math.floor(Math.random() * zone.pois.length)];
      return { ...poi, zone: name, chatChance: zone.chatChance };
    }
  }
  const z = ZONES.office;
  const poi = z.pois[Math.floor(Math.random() * z.pois.length)];
  return { ...poi, zone: 'office', chatChance: z.chatChance };
}

function zoneChatLine(zoneName) {
  const z = ZONES[zoneName];
  if (!z) return 'hey!';
  return z.chats[Math.floor(Math.random() * z.chats.length)];
}

/* ── Character State ───────────────────────────────────────── */
let agentData = [], selectedAgent = null, frame = 0;
const sim = {};

function getSim(id) {
  if (sim[id]) return sim[id];
  const cfg = AGENT_CFG[id];
  const c = cfg ? cfg.sCol : 5, r = cfg ? cfg.sRow : 12;
  sim[id] = {
    st: 'sit', col: c, row: r,
    x: c * T + T / 2, y: r * T + T / 2,
    path: [], pi: 0, mp: 0, dir: 'down',
    wf: 0, wt: 0, it: 2 + Math.random() * 4, ct: 0, cl: '', wc: 0,
  };
  return sim[id];
}

function updSim(id, as, dt) {
  const s = getSim(id), cfg = AGENT_CFG[id];
  if (!cfg) return;
  const active = as === 'WORKING' || as === 'STARTING';
  const off = as === 'OFFLINE';

  if (active) {
    if (s.st !== 'sit') {
      if (s.col === cfg.sCol && s.row === cfg.sRow) {
        s.st = 'sit'; s.dir = 'up'; s.path = [];
      } else if (s.st !== 'walk' || !s.path.length) {
        const pp = findPath(s.col, s.row, cfg.sCol, cfg.sRow);
        if (pp.length) { s.path = pp; s.pi = 0; s.mp = 0; s.st = 'walk'; }
        else { s.col = cfg.sCol; s.row = cfg.sRow; s.x = s.col * T + T / 2; s.y = s.row * T + T / 2; s.st = 'sit'; s.dir = 'up'; }
      }
    }
    if (s.st === 'sit') s.dir = 'up';
  } else if (off) {
    s.col = cfg.sCol; s.row = cfg.sRow; s.x = s.col * T + T / 2; s.y = s.row * T + T / 2;
    s.st = 'sit'; s.dir = 'down'; s.path = [];
  } else {
    if (s.st === 'sit' || s.st === 'idle_sit') {
      s.it -= dt;
      if (s.it <= 0) {
        const t = pickZonePOI();
        const pp = findPath(s.col, s.row, t.c, t.r);
        if (pp.length) {
          s.path = pp; s.pi = 0; s.mp = 0; s.st = 'walk'; s.wc++;
          s._destPOI = t;
        }
        s.it = 3 + Math.random() * 5;
      }
    } else if (s.st === 'stand' || s.st === 'chat') {
      s.it -= dt; s.ct -= dt;
      if (s.ct <= 0) s.st = 'stand';
      if (s.it <= 0) {
        if (s.wc > 4 + Math.floor(Math.random() * 3)) {
          const pp = findPath(s.col, s.row, cfg.sCol, cfg.sRow);
          if (pp.length) { s.path = pp; s.pi = 0; s.mp = 0; s.st = 'walk'; s._goSeat = true; }
          s.wc = 0;
        } else {
          const t = pickZonePOI();
          const pp = findPath(s.col, s.row, t.c, t.r);
          if (pp.length) {
            s.path = pp; s.pi = 0; s.mp = 0; s.st = 'walk'; s._goSeat = false; s.wc++;
            s._destPOI = t;
          }
        }
        s.it = 2 + Math.random() * 4;
      }
    }
  }

  if (s.st === 'walk' && s.path.length) {
    s.mp += 2.5 * dt; s.wt += dt;
    if (s.wt > 0.12) { s.wf = (s.wf + 1) % 7; s.wt = 0; }
    while (s.mp >= 1 && s.pi < s.path.length) {
      s.mp -= 1;
      const n = s.path[s.pi];
      const dc = n.c - s.col, dr = n.r - s.row;
      if (dc > 0) s.dir = 'right'; else if (dc < 0) s.dir = 'left';
      else if (dr > 0) s.dir = 'down'; else s.dir = 'up';
      s.col = n.c; s.row = n.r; s.pi++;
    }
    if (s.pi < s.path.length) {
      const n = s.path[s.pi], fx = s.col * T + T / 2, fy = s.row * T + T / 2;
      const tx = n.c * T + T / 2, ty = n.r * T + T / 2;
      const t = Math.min(s.mp, 1);
      s.x = fx + (tx - fx) * t; s.y = fy + (ty - fy) * t;
    } else {
      s.x = s.col * T + T / 2; s.y = s.row * T + T / 2;
      if (s._goSeat && s.col === cfg.sCol && s.row === cfg.sRow) {
        s.st = 'sit'; s.dir = 'down'; s.it = 4 + Math.random() * 6;
      } else if (s._destPOI && s._destPOI.sit) {
        s.st = 'idle_sit'; s._sitDir = s._destPOI.sit; s.dir = s._destPOI.sit;
        s._zone = s._destPOI.zone; s.it = 4 + Math.random() * 6;
      } else {
        s.st = 'stand'; s.dir = 'down'; s.it = 2 + Math.random() * 4;
        s._zone = s._destPOI ? s._destPOI.zone : 'office';
      }
      s.path = [];
    }
  } else if (s.st !== 'walk') {
    s.x = s.col * T + T / 2; s.y = s.row * T + T / 2;
  }

  // Social — zone-aware chat
  if (s.st === 'stand' || s.st === 'idle_sit') {
    const chatChance = (s._zone === 'lounge' || s._zone === 'kitchen') ? 0.08 : 0.015;
    for (const oid of Object.keys(AGENT_CFG)) {
      if (oid === id) continue;
      const o = sim[oid];
      if (!o || o.st === 'sit' || o.st === 'walk') continue;
      if (Math.abs(s.col - o.col) + Math.abs(s.row - o.row) <= 2 && Math.random() < chatChance) {
        s.st = 'chat'; s.ct = 2 + Math.random() * 3;
        s.cl = zoneChatLine(s._zone || 'office');
        if (o.col > s.col) s.dir = 'right'; else if (o.col < s.col) s.dir = 'left';
        else if (o.row > s.row) s.dir = 'down'; else s.dir = 'up';
      }
    }
  }
}

/* ── Loading Screen ────────────────────────────────────────── */
function drawLoading() {
  ctx.fillStyle = '#1a1714'; ctx.fillRect(0, 0, CW, CH);
  ctx.font = '11px "Press Start 2P"'; ctx.fillStyle = '#4a9eff';
  ctx.textAlign = 'center';
  ctx.fillText('NAVAIA CREW HQ', CW / 2, CH / 2 - 30);
  ctx.font = '8px "Press Start 2P"'; ctx.fillStyle = '#fbbf24';
  ctx.fillText('LOADING OFFICE...', CW / 2, CH / 2);
  const bw = 200, bh = 12, bx = CW / 2 - bw / 2, by = CH / 2 + 20;
  ctx.strokeStyle = '#4a9eff'; ctx.lineWidth = 2; ctx.strokeRect(bx, by, bw, bh);
  const p = loadTotal > 0 ? loadCount / loadTotal : 0;
  ctx.fillStyle = '#4a9eff'; ctx.fillRect(bx + 2, by + 2, (bw - 4) * p, bh - 4);
  ctx.font = '7px "Press Start 2P"'; ctx.fillStyle = '#555';
  ctx.fillText(`${loadCount}/${loadTotal}`, CW / 2, by + bh + 16);
  ctx.textAlign = 'left';
}

/* ── Game Loop ─────────────────────────────────────────────── */
let prevTime = 0;

function loop(time) {
  const dt = prevTime ? Math.min((time - prevTime) / 1000, 0.1) : 0.016;
  prevTime = time;

  if (!assetsReady) { drawLoading(); requestAnimationFrame(loop); return; }

  for (const a of agentData) updSim(a.id, a.state || 'OFFLINE', dt);

  ctx.clearRect(0, 0, CW, CH);
  drawTiles();

  const scene = [...wallFaceObjs(), ...furnObjs(), ...charObjs()];
  scene.sort((a, b) => a.zY - b.zY);
  for (const o of scene) o.draw();

  drawOverlays();
  frame++;
  requestAnimationFrame(loop);
}

/* ── Interaction ───────────────────────────────────────────── */
canvas.addEventListener('click', e => {
  const rc = canvas.getBoundingClientRect();
  const mx = (e.clientX - rc.left) * CW / rc.width;
  const my = (e.clientY - rc.top) * CH / rc.height;
  for (const a of agentData) {
    const s = sim[a.id]; if (!s) continue;
    if (mx >= s.x - T && mx <= s.x + T && my >= s.y - 2 * T && my <= s.y + T) { selectAgent(a); return; }
  }
  deselectAgent();
});

function escapeHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function selectAgent(a) {
  selectedAgent = a.id;
  document.getElementById('agent-detail').style.display = 'block';
  const cfg = AGENT_CFG[a.id] || {};
  document.getElementById('detail-header').textContent = `${cfg.name || a.name} — ${a.role}`;
  document.getElementById('detail-header').style.color = cfg.color || '#fff';
  document.getElementById('detail-info').innerHTML = `
    <div style="margin-bottom:8px"><span class="agent-state ${a.state}">${a.state}</span></div>
    <div style="font-size:16px;margin-bottom:4px">Model: <b>${a.model}</b></div>
    <div style="font-size:16px;margin-bottom:4px">Tasks: <b>${a.task_count}</b></div>
    ${a.current_task ? `<div style="font-size:16px;color:var(--text-dim)">Working on: ${escapeHtml(a.current_task)}</div>` : ''}`;
  window._officeAgentId = a.id;
}

function deselectAgent() {
  selectedAgent = null;
  document.getElementById('agent-detail').style.display = 'none';
}

async function assignFromOffice(e) {
  e.preventDefault();
  const t = document.getElementById('office-task-title').value;
  const d = document.getElementById('office-task-desc').value;
  if (!t || !window._officeAgentId) return;
  await CrewHQ.createTask(window._officeAgentId, t, d);
  document.getElementById('office-task-title').value = '';
  document.getElementById('office-task-desc').value = '';
}

/* ── Init ──────────────────────────────────────────────────── */
requestAnimationFrame(loop);

loadAssets().then(() => modernizeFurniture()).then(() => {
  buildNavGrid();
  assetsReady = true;
  console.log('Pixel Office v8: Loaded', loadCount, 'assets — modern white furniture');
});

CrewHQ.onUpdate(state => {
  document.getElementById('conn-dot').className = 'status-dot online';
  agentData = state.agents || [];
});
