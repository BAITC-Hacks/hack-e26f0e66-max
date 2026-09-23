/* Money Graph — standalone interface.
 *
 * Reads output_files/web_data.json, which the pipeline writes, and renders
 * everything client-side. No build step, no framework, no network: vis-network
 * is vendored locally, so this works on an air-gapped machine.
 *
 * It shows the same numbers as the Gradio interface because both read the same
 * exported artifacts. Evidence, `why` and hypotheses arrive pre-rendered in all
 * three languages, rebuilt from each node's rule trace rather than translated.
 */
'use strict';

let D = null;                      // the whole payload
let LANG = 'en';
let NODES = new Map();             // gid -> node
let OUT = new Map(), IN = new Map();
let TAB = 'about';
let net = null;                    // live vis-network instance

/* ------------------------------------------------------------- helpers */
const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = s => String(s ?? '').replace(/[&<>"]/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function t(key, fmt) {
  const entry = D.i18n.ui[key];
  let s = entry ? (entry[LANG] || entry.en || key) : key;
  if (fmt) for (const k in fmt) s = s.replaceAll('{' + k + '}', fmt[k]);
  return s;
}
const roleName = r => (D.i18n.role_names[r]?.[LANG]) || (D.i18n.role_names[r]?.en) || r;
const roleMeaning = r => (D.i18n.role_meaning[r]?.[LANG]) || (D.i18n.role_meaning[r]?.en) || '';
const color = r => D.role_colors[r] || '#8b95a3';

/* Money, in the conventions of the selected language. */
function kzt(x) {
  if (x === null || x === undefined || Number.isNaN(x)) return '—';
  const u = LANG === 'en' ? ['M KZT', 'k KZT', 'KZT'] : ['млн ₸', LANG === 'kk' ? 'мың ₸' : 'тыс. ₸', '₸'];
  const a = Math.abs(x);
  if (a >= 1e6) return (x / 1e6).toFixed(1) + ' ' + u[0];
  if (a >= 1e3) return Math.round(x / 1e3) + ' ' + u[1];
  return Math.round(x).toLocaleString('fr-FR').replace(/ | /g, ' ') + ' ' + u[2];
}
const num = x => (x ?? 0).toLocaleString('fr-FR').replace(/ | /g, ' ');

/* --------------------------------------------------------------- boot */
async function boot() {
  try {
    const res = await fetch('data/web_data.json', { cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    D = await res.json();
  } catch (e) {
    $('#boot-msg').innerHTML =
      '<b>Could not load the results.</b><br><br>' +
      'Run the pipeline first:<br><code>./agent_run.sh</code><br><br>' +
      '<span class="muted">' + esc(e.message) + '</span>';
    $('.spinner').style.display = 'none';
    return;
  }

  for (const n of D.nodes) NODES.set(n.gid, n);
  for (const e of D.edges) {
    if (!OUT.has(e.s)) OUT.set(e.s, []);
    if (!IN.has(e.d)) IN.set(e.d, []);
    OUT.get(e.s).push(e);
    IN.get(e.d).push(e);
  }

  LANG = localStorage.getItem('mg-lang') || 'en';
  if (!D.i18n.languages[LANG]) LANG = 'en';
  document.documentElement.dataset.theme = localStorage.getItem('mg-theme') || 'light';

  buildLangs();
  $('#theme-btn').onclick = () => {
    const d = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = d;
    localStorage.setItem('mg-theme', d);
    if (TAB === 'account' || TAB === 'groups') render();
  };
  render();
  $('#boot').classList.add('gone');
  setTimeout(() => $('#boot').remove(), 350);
}

function buildLangs() {
  const box = $('#langs');
  box.innerHTML = '';
  for (const [code, name] of Object.entries(D.i18n.languages)) {
    const b = el('button', code === LANG ? 'on' : '', esc(name));
    b.onclick = () => {
      LANG = code;
      localStorage.setItem('mg-lang', code);
      buildLangs();
      render();
    };
    box.appendChild(b);
  }
}

const TABS = ['about', 'start', 'priority', 'account', 'groups', 'agents',
              'data', 'cost', 'downloads'];
const TAB_KEY = {
  about: 'tab.about', start: 'tab.start', priority: 'tab.priority',
  account: 'tab.account', groups: 'tab.groups', agents: 'tab.agents',
  data: 'tab.data', cost: 'tab.cost', downloads: 'tab.downloads',
};

function render() {
  document.documentElement.lang = LANG;
  const mt = D.i18n.machine_translated.includes(LANG);
  const banner = $('#mt-banner');
  banner.hidden = !mt;
  if (mt) banner.innerHTML = D.i18n.ui['mt.warning'][LANG] || '';

  $('[data-i18n-track]').textContent = 'Track 2 — Finances · HackAlem AI';

  const nav = $('#tabs');
  nav.innerHTML = '';
  for (const id of TABS) {
    const b = el('button', id === TAB ? 'on' : '', esc(t(TAB_KEY[id])));
    b.onclick = () => { TAB = id; render(); window.scrollTo({ top: 0 }); };
    nav.appendChild(b);
  }

  const m = $('#main');
  m.innerHTML = '';
  ({ about: tabAbout, start: tabStart, priority: tabPriority,
     account: tabAccount, groups: tabGroups, agents: tabAgents,
     data: tabData, cost: tabCost, downloads: tabDownloads }[TAB])(m);

  const meta = D.meta;
  $('#foot-meta').textContent =
    `${num(meta.n_nodes)} · ${num(meta.n_edges)} · ${meta.n_clusters}`;
  $('#foot-note').textContent = t('about.safety').replace(/<[^>]+>/g, '').slice(0, 130) + '…';
}

/* ------------------------------------------------------------- pieces */
// Both halves take HTML: the translations themselves contain <b> tags, and
// the account header carries a coloured role pill. Anything that comes from the
// data rather than from our own strings is escaped at the call site.
function hero(h, p) { return el('div', 'hero', `<h2>${h}</h2><p>${p}</p>`); }
function note(html) { return el('div', 'note', html); }
function warnBox(html) { return el('div', 'warn', html); }
function sec(text) { return el('h3', 'sec', esc(text)); }

function kpis(items) {
  const box = el('div', 'kpis');
  for (const [v, l, s] of items) {
    box.appendChild(el('div', 'kpi',
      `<div class="v">${esc(v)}</div><div class="l">${esc(l)}</div>` +
      (s ? `<div class="s">${esc(s)}</div>` : '')));
  }
  return box;
}

function table(headers, rows, opts = {}) {
  const wrap = el('div', 'panel');
  const scroll = el('div', 'scroll');
  const tb = el('table', 'data');
  tb.innerHTML = '<thead><tr>' +
    headers.map(h => `<th${h.num ? ' class="num"' : ''}>${esc(h.label ?? h)}</th>`).join('') +
    '</tr></thead>';
  const body = el('tbody');
  rows.forEach((r, i) => {
    const tr = el('tr', opts.onRow ? 'click' : '');
    tr.innerHTML = r.map((c, j) =>
      `<td${headers[j] && headers[j].num ? ' class="num"' : ''}>${c}</td>`).join('');
    if (opts.onRow) tr.onclick = () => {
      [...body.children].forEach(x => x.classList.remove('on'));
      tr.classList.add('on');
      opts.onRow(i);
    };
    body.appendChild(tr);
  });
  tb.appendChild(body);
  scroll.appendChild(tb);
  wrap.appendChild(scroll);
  return wrap;
}

function roleBars() {
  const counts = Object.entries(D.meta.role_counts).sort((a, b) => b[1] - a[1]);
  const total = counts.reduce((s, [, n]) => s + n, 0);
  const widest = counts[0] ? counts[0][1] : 1;
  const box = el('div', 'bars');
  for (const [role, n] of counts) {
    box.appendChild(el('div', 'bar',
      `<div class="nm"><span class="sw" style="background:${color(role)}"></span>` +
      `${esc(roleName(role))}</div>` +
      `<div class="track" title="${esc(roleMeaning(role))}">` +
      `<div class="fill" style="width:${Math.max(1.2, 100 * n / widest).toFixed(1)}%;` +
      `background:${color(role)}"></div></div>` +
      `<div class="ct">${num(n)}<span>${Math.round(100 * n / total)}%</span></div>`));
  }
  return box;
}

function legend() {
  const box = el('div', 'legend');
  let html = `<h4>${esc(t('legend.colors'))}</h4>`;
  for (const role of Object.keys(D.role_colors)) {
    html += `<div class="row"><span class="sw" style="background:${color(role)}"></span>` +
            `<b>${esc(roleName(role))}</b> <span>— ${esc(roleMeaning(role))}</span></div>`;
  }
  html += `<h4>${esc(t('legend.shapes'))}</h4>`;
  for (const k of ['legend.diamond', 'legend.circle', 'legend.dashed',
                   'legend.arrow', 'legend.width', 'legend.size']) {
    html += `<div class="row"><span>${t(k)}</span></div>`;
  }
  box.innerHTML = html;
  return box;
}

/* --------------------------------------------------------------- graph */
function drawGraph(container, gids, centre, showAmounts) {
  const keep = new Set(gids);
  const nodes = [...keep].map(gid => {
    const n = NODES.get(gid);
    const traced = n.outflow_observed !== false;
    const isCentre = gid === centre;
    return {
      id: gid,
      label: String(gid).slice(-6),
      title: `${t('col.account')} ${gid}\n${roleName(n.role).toUpperCase()} — ${roleMeaning(n.role)}\n` +
        '─'.repeat(30) + `\n${t('f.priority')}: ${(n.priority_score ?? 0).toFixed(3)}\n` +
        `${t('f.confidence')}: ${(n.role_score ?? 0).toFixed(2)}\n` +
        `${t('f.received')}: ${kzt(n.in_sum)} (${n.in_deg})\n` +
        `${t('f.sent')}: ${kzt(n.out_sum)} (${n.out_deg})\n` +
        '─'.repeat(30) + `\n${n.evidence[LANG]}`,
      shape: n.is_seed ? 'diamond' : 'dot',
      size: isCentre ? 30 : 12 + 20 * (n.priority_score ?? 0),
      borderWidth: isCentre ? 5 : (traced ? 1 : 3),
      shapeProperties: { borderDashes: traced ? false : [5, 4] },
      color: {
        background: color(n.role),
        border: isCentre ? '#111' : (traced ? '#8d99a4' : '#cc3b3b'),
        highlight: { background: color(n.role), border: '#000' },
      },
    };
  });
  const edges = D.edges
    .filter(e => keep.has(e.s) && keep.has(e.d))
    .map(e => ({
      from: e.s, to: e.d, value: Math.log1p(e.v),
      title: `${Math.round(e.v).toLocaleString('fr-FR')} KZT · ${e.n}`,
      label: showAmounts ? kzt(e.v) : undefined,
    }));

  if (net) { net.destroy(); net = null; }
  const dark = document.documentElement.dataset.theme === 'dark';

  // Spacing has to scale with size. A fixed spring length that looks right for
  // a 12-node ego map packs a 200-node cluster into an unreadable ball, so the
  // repulsion, the spring length and the settling time all grow with the node
  // count.
  const N = nodes.length;
  const springLength = Math.round(Math.min(620, 150 + N * 1.9));
  const gravity = -Math.round(Math.min(48000, 9000 + N * 145));
  const iterations = Math.round(Math.min(900, 260 + N * 2.2));

  net = new vis.Network(container, { nodes, edges }, {
    // Physics on briefly, then frozen: the layout settles into something
    // readable instead of the tight ball vis produces from a cold start.
    physics: {
      enabled: true, solver: 'barnesHut',
      barnesHut: { gravitationalConstant: gravity, springLength: springLength,
                   springConstant: .014, avoidOverlap: 1, damping: .6,
                   centralGravity: N > 60 ? .12 : .3 },
      stabilization: { enabled: true, iterations: iterations, fit: true },
      maxVelocity: 40, minVelocity: .8,
    },
    layout: { randomSeed: D.meta.seed },
    nodes: { font: { size: 13, color: dark ? '#e9edf2' : '#16191d',
                     strokeWidth: 5, strokeColor: dark ? '#171b21' : '#fff' } },
    edges: {
      arrows: { to: { enabled: true, scaleFactor: .5 } },
      color: { color: dark ? '#3a444f' : '#ccd4db', highlight: dark ? '#8fa3b6' : '#44525f' },
      smooth: { type: 'curvedCW', roundness: .12 },
      scaling: { min: 1, max: 7 },
      font: { size: 11, align: 'top', color: dark ? '#a3aebd' : '#5a6472',
              strokeWidth: 5, strokeColor: dark ? '#171b21' : '#fff' },
    },
    interaction: { hover: true, tooltipDelay: 120, navigationButtons: true, keyboard: false },
  });
  net.once('stabilizationIterationsDone', () => net.setOptions({ physics: false }));
  net.on('doubleClick', p => {
    if (p.nodes.length) { openAccount(p.nodes[0]); }
  });
}

function egoGids(gid, hops) {
  let keep = new Set([gid]), frontier = new Set([gid]);
  for (let h = 0; h < hops; h++) {
    const next = new Set();
    for (const g of frontier) {
      (OUT.get(g) || []).forEach(e => next.add(e.d));
      (IN.get(g) || []).forEach(e => next.add(e.s));
    }
    next.forEach(x => keep.add(x));
    frontier = next;
  }
  if (keep.size > 300) {
    const best = D.edges.filter(e => keep.has(e.s) && keep.has(e.d))
      .sort((a, b) => b.v - a.v).slice(0, 300);
    keep = new Set([gid]);
    best.forEach(e => { keep.add(e.s); keep.add(e.d); });
  }
  return [...keep];
}

/* ---------------------------------------------------------------- tabs */
function tabAbout(m) {
  m.appendChild(hero(t('about.title'), t('about.lead')));
  m.appendChild(sec(t('about.steps')));
  const cards = el('div', 'cards');
  ['about.step1', 'about.step2', 'about.step3']
    .forEach(k => cards.appendChild(el('div', 'card', t(k))));
  m.appendChild(cards);
  m.appendChild(sec(t('about.map')));
  m.appendChild(table(
    [t('about.col.tab'), t('about.col.for'), t('about.col.when')],
    D.i18n.tab_guide.map(g => [
      `<b>${esc(t(g.key))}</b>`,
      esc(g.for[LANG] || g.for.en),
      `<span class="muted">${esc(g.when[LANG] || g.when.en)}</span>`])));
  m.appendChild(note(t('about.safety')));
  m.appendChild(metaKpis());
}

function metaKpis() {
  const x = D.meta;
  return kpis([
    [num(x.n_nodes), t('kpi.accounts'), t('kpi.accounts.sub')],
    [String(D.top.length), t('kpi.shortlist'), t('kpi.shortlist.sub')],
    [kzt(x.turnover_kzt).split(' ')[0], t('kpi.turnover'), t('kpi.turnover.sub')],
    [String(x.n_clusters), t('kpi.groups'), t('kpi.groups.sub')],
    [String(x.n_frontier), t('kpi.frontier'), t('kpi.frontier.sub')],
  ]);
}

function tabStart(m) {
  m.appendChild(hero(t('start.title'), t('start.lead')));
  m.appendChild(note(t('purpose.start')));
  m.appendChild(metaKpis());
  m.appendChild(sec(t('start.classified')));
  const split = el('div', 'split');
  const left = el('div', 'panel');
  left.appendChild(el('div', 'panel-pad')).appendChild(roleBars());
  split.appendChild(left);
  split.appendChild(legend());
  m.appendChild(split);
  m.appendChild(note(t('start.artifacts')));
}

function tabPriority(m) {
  m.appendChild(hero(t('prio.title'), t('prio.lead')));
  m.appendChild(note(t('purpose.priority')));
  m.appendChild(note(t('prio.note')));
  const detail = el('div');
  const rows = D.top.map(r => {
    const n = NODES.get(r.gid) || {};
    return [
      `<b>${r.rank}</b>`,
      `<span class="mono">${r.gid}</span>`,
      `<span class="pill" style="background:${color(r.role)}">${esc(roleName(r.role))}</span>`,
      r.priority_score.toFixed(3),
      esc(r.why[LANG]) + flagChips(n),
    ];
  });
  m.appendChild(table(
    [t('col.rank'), t('col.account'), t('col.role'),
     { label: t('col.priority'), num: true }, t('col.why')],
    rows, { onRow: i => showDetail(detail, D.top[i].gid) }));
  m.appendChild(sec(t('prio.selected')));
  m.appendChild(note(t('prio.clickhint')));
  m.appendChild(detail);
  showDetail(detail, D.top[0].gid);
}

function flagChips(n) {
  const f = [];
  if (n.flag_near_threshold) f.push('near-threshold');
  if (n.flag_round_amounts) f.push('round amounts');
  if (n.flag_extreme_for_hop) f.push('extreme for hop');
  return f.length ? '<br>' + f.map(x => `<span class="flag">⚑ ${x}</span>`).join('') : '';
}

function showDetail(host, gid) {
  host.innerHTML = '';
  host.appendChild(accountCard(gid));
  host.appendChild(whyPanel(gid));
}

function accountCard(gid) {
  const n = NODES.get(gid);
  if (!n) return warnBox(t('acc.notfound', { gid }));
  const traced = n.outflow_observed !== false;
  const rows = [
    [t('f.priority'), `<b>${(n.priority_score ?? 0).toFixed(3)}</b>`],
    [t('f.confidence'), (n.role_score ?? 0).toFixed(2)],
    [t('f.received'), `${kzt(n.in_sum)} ${t('f.payers_n', { n: n.in_deg })}`],
    [t('f.sent'), `${kzt(n.out_sum)} ${t('f.recipients_n', { n: n.out_deg })}`],
    [t('f.reach'), `${n.seed_reach ?? 0} / ${D.meta.n_seeds}`],
    [t('f.attributed'), kzt(n.seed_kzt_attributed)],
    [t('f.depth'), String(n.depth)],
    [t('f.isseed'), n.is_seed ? t('yes') : t('no')],
    [t('f.cluster'), String(n.cluster_id)],
  ];
  const box = el('div');
  box.appendChild(hero(
    `${esc(t('col.account'))} <span class="mono">${esc(gid)}</span>` +
    ` <span class="pill" style="background:${color(n.role)}">${esc(roleName(n.role))}</span>`,
    esc(roleMeaning(n.role))));
  const p = el('div', 'panel');
  const pad = el('div', 'panel-pad');
  pad.innerHTML = '<table class="facts">' +
    rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v}</td></tr>`).join('') + '</table>';
  p.appendChild(pad);
  box.appendChild(p);
  box.appendChild(note(`<b>${esc(t('acc.evidence'))}.</b> ${esc(n.evidence[LANG])}`));
  if (!traced) box.appendChild(warnBox(t('acc.frontier_warn')));
  if (n.secondary_roles) {
    box.appendChild(note(`${esc(t('acc.also'))}: <b>` +
      String(n.secondary_roles).split(';').filter(Boolean).map(r => esc(roleName(r))).join(', ') +
      '</b>'));
  }
  if (n.critic_caveat) {
    box.appendChild(warnBox(`<b>${esc(t('acc.caveat'))}.</b> ` +
      esc(n.critic_caveat).replaceAll(' | ', '<br><br>')));
  }
  const chips = flagChips(n);
  if (chips) box.appendChild(el('div', '', chips));
  return box;
}

function whyPanel(gid) {
  const n = NODES.get(gid);
  const tr = n?.trace || {};
  const box = el('div', 'panel');
  const pad = el('div', 'panel-pad');
  let h = `<h3 class="sec" style="margin-top:0">${esc(t('why.heading'))}</h3>`;
  h += `<p class="hint">${esc(t('why.lead').replace(/\*/g, ''))}</p>`;
  if (tr.gate) {
    h += `<p>${t('why.rule').replace(/\*\*/g, '')}</p>` +
         `<div class="note mono">${esc(tr.gate)}</div>`;
  }
  const sub = (title, obj) => {
    if (!obj || !Object.keys(obj).length) return '';
    return `<p>${title.replace(/\*\*/g, '').replace(/\*/g, '')}</p><table class="facts">` +
      Object.entries(obj).map(([k, v]) =>
        `<tr><td>${esc(k)}</td><td>${esc(fmtVal(v))}</td></tr>`).join('') + '</table>';
  };
  h += sub(t('why.values'), tr.metrics);
  h += sub(t('why.thresholds'), tr.thresholds);
  if (tr.penalties?.length) {
    h += `<p>${t('why.penalties').replace(/\*\*/g, '')}</p><ul>` +
      tr.penalties.map(p => `<li>${esc(p)}</li>`).join('') + '</ul>';
  }
  if (tr.notes?.length) h += '<ul>' + tr.notes.map(p => `<li>${esc(p)}</li>`).join('') + '</ul>';
  if (n?.priority_adjustments) {
    h += `<p>${t('why.adjust').replace(/\*\*/g, '')} ${esc(n.priority_adjustments)}</p>`;
  }
  const d = D.dossiers[String(gid)];
  if (d) {
    h += `<h3 class="sec">${esc(t('dossier.heading'))}</h3>` +
         `<p>${t('dossier.pattern').replace(/\*\*/g, '')} ${esc(d.pattern || '—')}</p>` +
         `<p>${esc(d.summary || '')}</p>`;
    if (d.alternative_explanation) {
      h += `<div class="note">${t('dossier.alt').replace(/\*\*/g, '')} ${esc(d.alternative_explanation)}</div>`;
    }
    if (d.next_step) h += `<p>${t('dossier.next').replace(/\*\*/g, '')} ${esc(d.next_step)}</p>`;
    h += `<p class="hint">${esc(t('dossier.advisory').replace(/\*/g, ''))}</p>`;
  }
  pad.innerHTML = h;
  box.appendChild(pad);
  return box;
}

const fmtVal = v => v === null || v === undefined ? '—'
  : typeof v === 'boolean' ? (v ? '✓' : '✗')
  : typeof v === 'number' ? (Math.abs(v) < 1e5 ? v.toLocaleString('fr-FR', { maximumFractionDigits: 2 })
                                               : Math.round(v).toLocaleString('fr-FR'))
  : String(v);

let accState = { gid: null, hops: 1, amounts: false };

function openAccount(gid) { accState.gid = gid; TAB = 'account'; render(); window.scrollTo({ top: 0 }); }

function tabAccount(m) {
  if (!accState.gid) accState.gid = D.top[0].gid;
  m.appendChild(hero(t('acc.title'), t('acc.lead')));
  m.appendChild(note(t('purpose.account')));

  const tools = el('div', 'graph-tools');
  const f1 = el('div', 'field');
  f1.innerHTML = `<span class="lab">${esc(t('acc.input'))}</span>`;
  const input = el('input');
  input.type = 'search';
  input.placeholder = t('acc.placeholder');
  input.value = accState.gid;
  input.setAttribute('list', 'gid-list');
  f1.appendChild(input);
  const dl = el('datalist');
  dl.id = 'gid-list';
  dl.innerHTML = D.top.map(r => `<option value="${r.gid}">`).join('');
  f1.appendChild(dl);
  tools.appendChild(f1);

  const go = el('button', 'btn primary', t('ask.send'));
  const apply = () => {
    const v = parseInt(String(input.value).trim(), 10);
    if (!Number.isNaN(v)) { accState.gid = v; render(); }
  };
  go.onclick = apply;
  input.onkeydown = e => { if (e.key === 'Enter') apply(); };
  tools.appendChild(go);

  const f2 = el('div', 'field');
  f2.innerHTML = `<span class="lab">${esc(t('acc.hops'))}</span>`;
  const sel = el('select');
  sel.innerHTML = '<option value="1">1</option><option value="2">2</option>';
  sel.value = String(accState.hops);
  sel.onchange = () => { accState.hops = +sel.value; render(); };
  f2.appendChild(sel);
  tools.appendChild(f2);

  const lab = el('label', 'inline');
  const cb = el('input');
  cb.type = 'checkbox';
  cb.checked = accState.amounts;
  cb.onchange = () => { accState.amounts = cb.checked; render(); };
  lab.appendChild(cb);
  lab.appendChild(document.createTextNode(t('acc.amounts')));
  tools.appendChild(lab);
  m.appendChild(tools);
  m.appendChild(el('div', 'hint', esc(t('acc.hops.info'))));

  const split = el('div', 'split');
  split.appendChild(accountCard(accState.gid));
  split.appendChild(whyPanel(accState.gid));
  m.appendChild(split);

  m.appendChild(sec(t('acc.mapheading')));
  m.appendChild(note(t('map.guide')));
  const g = el('div', 'graph');
  m.appendChild(el('div', 'graphwrap')).appendChild(g);
  m.appendChild(legend());

  const links = el('div', 'split');
  links.appendChild(linkTable(t('acc.payers'), IN.get(accState.gid) || [], 's'));
  links.appendChild(linkTable(t('acc.recipients'), OUT.get(accState.gid) || [], 'd'));
  m.appendChild(links);

  requestAnimationFrame(() =>
    drawGraph(g, egoGids(accState.gid, accState.hops), accState.gid, accState.amounts));
}

function linkTable(title, edges, side) {
  const box = el('div');
  box.appendChild(sec(title));
  const rows = [...edges].sort((a, b) => b.v - a.v).slice(0, 60).map(e => {
    const other = side === 's' ? e.s : e.d;
    const n = NODES.get(other) || {};
    return [
      `<a href="#" class="mono" data-gid="${other}">${other}</a>`,
      `<span class="pill" style="background:${color(n.role)}">${esc(roleName(n.role))}</span>`,
      n.is_seed ? t('yes') : '',
      num(Math.round(e.v)),
      String(e.n),
    ];
  });
  const tb = table([t('col.account'), t('col.itsrole'), t('col.seedq'),
                    { label: t('col.amount'), num: true },
                    { label: t('col.transfers'), num: true }], rows);
  tb.addEventListener('click', ev => {
    const a = ev.target.closest('a[data-gid]');
    if (a) { ev.preventDefault(); openAccount(+a.dataset.gid); }
  });
  box.appendChild(tb);
  return box;
}

let grpState = { cid: null, amounts: false };

function tabGroups(m) {
  if (grpState.cid === null) grpState.cid = D.clusters[0].cluster_id;
  m.appendChild(hero(t('grp.title'), t('grp.lead')));
  m.appendChild(note(t('purpose.groups')));
  m.appendChild(table(
    [{ label: t('col.groupid'), num: true }, { label: t('col.naccounts'), num: true },
     { label: t('col.nseeds'), num: true }, { label: t('col.internal'), num: true },
     t('col.looks')],
    D.clusters.map(c => [String(c.cluster_id), num(c.n_nodes), num(c.n_seed),
                         kzt(c.sum_kzt_internal), esc(c.hypothesis[LANG])]),
    { onRow: i => { grpState.cid = D.clusters[i].cluster_id; render(); } }));
  m.appendChild(note(t('grp.note')));

  const tools = el('div', 'graph-tools');
  const f = el('div', 'field');
  f.innerHTML = `<span class="lab">${esc(t('grp.show'))}</span>`;
  const sel = el('select');
  sel.innerHTML = D.clusters.map(c =>
    `<option value="${c.cluster_id}">${c.cluster_id} (${c.n_nodes})</option>`).join('');
  sel.value = String(grpState.cid);
  sel.onchange = () => { grpState.cid = +sel.value; render(); };
  f.appendChild(sel);
  tools.appendChild(f);
  const lab = el('label', 'inline');
  const cb = el('input');
  cb.type = 'checkbox';
  cb.checked = grpState.amounts;
  cb.onchange = () => { grpState.amounts = cb.checked; render(); };
  lab.appendChild(cb);
  lab.appendChild(document.createTextNode(t('acc.amounts')));
  tools.appendChild(lab);
  m.appendChild(tools);

  const c = D.clusters.find(x => x.cluster_id === grpState.cid);
  m.appendChild(hero(`${esc(t('grp.word'))} ${esc(c.cluster_id)}`,
    `<b>${num(c.n_nodes)}</b> ${esc(t('grp.accounts'))} · ` +
    `<b>${c.n_seed}</b> ${esc(t('grp.seeds'))} · ` +
    `<b>${kzt(c.sum_kzt_internal)}</b> ${esc(t('grp.internal'))}`));
  m.appendChild(note(`<b>${esc(t('grp.hypothesis'))}.</b> ${esc(c.hypothesis[LANG])}`));
  m.appendChild(note(t('map.guide')));
  const g = el('div', 'graph');
  // A 200-node group needs the room; a 3-node one does not.
  const size = D.nodes.filter(n => n.cluster_id === grpState.cid).length;
  g.style.height = Math.min(820, Math.max(520, 420 + size * 1.6)) + 'px';
  m.appendChild(el('div', 'graphwrap')).appendChild(g);
  m.appendChild(legend());

  let members = D.nodes.filter(n => n.cluster_id === grpState.cid)
    .sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0));
  const shown = members.slice(0, 400);
  if (members.length > 400) m.appendChild(warnBox(t('map.capped_cluster',
    { cap: 400, total: members.length })));
  const tb = table([t('col.account'), t('col.role'),
                    { label: t('col.priority'), num: true }, t('col.evidence')],
    members.slice(0, 200).map(n => [
      `<a href="#" class="mono" data-gid="${n.gid}">${n.gid}</a>`,
      `<span class="pill" style="background:${color(n.role)}">${esc(roleName(n.role))}</span>`,
      (n.priority_score ?? 0).toFixed(3), esc(n.evidence[LANG])]));
  tb.addEventListener('click', ev => {
    const a = ev.target.closest('a[data-gid]');
    if (a) { ev.preventDefault(); openAccount(+a.dataset.gid); }
  });
  m.appendChild(sec(t('grp.members')));
  m.appendChild(tb);

  requestAnimationFrame(() =>
    drawGraph(g, shown.map(n => n.gid), null, grpState.amounts));
}

function tabAgents(m) {
  m.appendChild(hero(t('ag.title'), t('ag.lead')));
  m.appendChild(note(t('purpose.agents')));
  const cal = D.calibration || {};
  if (cal.thresholds && Object.keys(cal.thresholds).length) {
    m.appendChild(sec(t('ag.thresholds')));
    m.appendChild(note(t('ag.thresholds.note')));
    m.appendChild(table([t('col.threshold'), { label: t('col.value'), num: true },
                         t('col.whychosen')],
      Object.entries(cal.thresholds).map(([k, v]) =>
        [`<span class="mono">${esc(k)}</span>`, String(v),
         esc((cal.rationale || {})[k] || '—')])));
  }
  const doss = Object.entries(D.dossiers || {});
  if (doss.length) {
    m.appendChild(sec(t('ag.dossiers')));
    m.appendChild(note(t('ag.dossiers.note')));
    m.appendChild(table([t('col.account'), t('col.pattern'), t('col.found'),
                         t('col.alt'), t('col.next')],
      doss.map(([gid, d]) => [
        `<a href="#" class="mono" data-gid="${gid}">${gid}</a>`,
        esc(d.pattern || ''), esc(d.summary || ''),
        esc(d.alternative_explanation || ''), esc(d.next_step || '')])));
    m.lastChild.addEventListener('click', ev => {
      const a = ev.target.closest('a[data-gid]');
      if (a) { ev.preventDefault(); openAccount(+a.dataset.gid); }
    });
  }
  m.appendChild(docAccordion(t('ag.critic'), D.docs.review_notes, true, t('ag.critic.note')));
  m.appendChild(docAccordion(t('ag.log'), D.docs.agent_log));
  m.appendChild(docAccordion(t('ag.requests'), D.docs.data_requests));
  if (D.docs.extras_report) m.appendChild(docAccordion('Optional analyses', D.docs.extras_report));
}

function docAccordion(title, text, open, noteHtml) {
  const d = el('details', 'acc');
  if (open) d.open = true;
  d.appendChild(el('summary', '', esc(title)));
  const body = el('div', 'body');
  if (noteHtml) body.appendChild(note(noteHtml));
  body.appendChild(el('pre', 'doc', esc(text || '—')));
  d.appendChild(body);
  return d;
}

function tabData(m) {
  m.appendChild(hero(t('data.title'), t('data.lead')));
  m.appendChild(note(t('purpose.data')));
  const p = D.ingest || {};
  m.appendChild(sec(t('data.files')));
  const used = Object.entries(p.used || {});
  const box = el('div', 'panel');
  const pad = el('div', 'panel-pad');
  pad.innerHTML = '<table class="facts">' + used.map(([k, v]) =>
    `<tr><td>${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`).join('') + '</table>';
  box.appendChild(pad);
  m.appendChild(box);
  m.appendChild((p.derived || []).length
    ? warnBox(t('data.derived') + '<ul>' +
        p.derived.map(d => `<li>${esc(d)}</li>`).join('') + '</ul>')
    : note(t('data.allsupplied')));
  m.appendChild(sec(t('data.mapping')));
  m.appendChild(note(t('data.mapping.note')));
  const rows = [];
  for (const f of (p.files || [])) {
    for (const [canon, col] of Object.entries(f.mapping || {})) {
      rows.push([esc(f.file), esc(f.kind), `<span class="mono">${esc(canon)}</span>`,
                 `<span class="mono">${esc(col)}</span>`,
                 esc((f.resolved_by || {})[canon] || '?')]);
    }
  }
  m.appendChild(table([t('col.file'), t('col.readas'), t('col.stdfield'),
                       t('col.yourcol'), t('col.matchedby')], rows));
  m.appendChild(note(t('data.own')));
  m.appendChild(docAccordion(t('data.profile'), D.docs.profile_report));
}

function tabCost(m) {
  m.appendChild(hero(t('cost.title'), t('cost.lead')));
  m.appendChild(note(t('purpose.cost')));
  const tr = D.trace || {}, tot = tr.totals || {};
  const cost = tot.cost_usd;
  m.appendChild(kpis([
    [(tr.total_runtime_s ?? 0).toFixed(0) + 's', t('cost.runtime'),
     t('cost.budget', { n: Math.round(tr.runtime_budget_s ?? 300) })],
    [String(tot.n_calls ?? 0), t('cost.calls'),
     tot.n_failed ? t('cost.failed', { n: tot.n_failed }) : t('cost.allok')],
    [num(tot.total_tokens ?? 0), t('cost.tokens'),
     t('cost.reasoning', { n: num(tot.reasoning_tokens ?? 0) })],
    [cost === null || cost === undefined ? t('cost.unpriced') : '$' + cost.toFixed(4),
     t('cost.spend'), t('cost.thisrun')],
  ]));
  m.appendChild(note(t('cost.note')));
  m.appendChild(docAccordion(t('tab.cost'), D.docs.run_trace, true));
}

function tabDownloads(m) {
  m.appendChild(hero(t('dl.title'), t('dl.lead')));
  m.appendChild(note(t('purpose.downloads')));
  const files = ['nodes_roles.csv', 'clusters.csv', 'top_nodes.csv',
    'node_features.parquet', 'graph_edges.parquet', 'profile_report.md',
    'data_requests.md', 'review_notes.md', 'agent_log.md', 'extras_report.md',
    'dossiers.json', 'extras.json', 'ingest_report.json',
    'run_trace.md', 'run_trace.json'];
  m.appendChild(table([t('col.file'), ''],
    files.map(f => [`<a href="data/${f}" download class="mono">${f}</a>`,
                    f.endsWith('.csv') && files.indexOf(f) < 3
                      ? '<b>required</b>' : '<span class="muted">support</span>'])));
  m.appendChild(note(t('dl.note')));
}

boot();
