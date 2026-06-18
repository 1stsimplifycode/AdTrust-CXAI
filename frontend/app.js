// ============================================================================
//  AdTrust CIOS — Autonomous Customer Intelligence Operating System
//  Bloomberg Terminal × Palantir Foundry × Tesla Fleet Intelligence
// ============================================================================

const api = (p, o) => fetch(p, o).then(r => r.json());
const $  = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

// ── State ──────────────────────────────────────────────────────────────────
let STATE = { twins: {}, selected: null, portfolio: {} };

const EMO_COLOR = {
  happiness: "#00ff88", satisfaction: "#00d4ff", excitement: "#ffaa00",
  curiosity: "#a855f7", loyalty: "#00e5c8", trust: "#2aa7c4",
  purchase_confidence: "#7fd0ff", frustration: "#ff6820",
  anger: "#ff2d6a", anxiety: "#9a7bff",
};
const trustColor = t => t.is_flagged ? "#ff2d6a" : (t.trust_score > 0.75 ? "#00ff88" : "#ffaa00");
const pct = x => (x * 100).toFixed(1) + "%";
const fx  = (x, d = 2) => Number(x).toFixed(d);
const pos = v => v >= 0 ? `+${fx(v)}` : fx(v);

// ── Boot ───────────────────────────────────────────────────────────────────
async function boot() {
  initNav();
  initClock();
  await refreshAll();
  setInterval(refreshAll, 30000);
}

function initClock() {
  const tick = () => {
    $('#sys-time').textContent = new Date().toISOString().replace('T', ' ').split('.')[0] + ' UTC';
  };
  tick();
  setInterval(tick, 1000);
}

function initNav() {
  $$('.mod-btn').forEach(btn => {
    btn.onclick = () => {
      $$('.mod-btn').forEach(b => b.classList.remove('active'));
      $$('.module').forEach(m => m.classList.remove('active'));
      btn.classList.add('active');
      const mod = btn.dataset.mod;
      $(`#mod-${mod}`)?.classList.add('active');
      // lazy-load module data
      if (mod === 'knowledge-graph') loadKnowledgeGraph();
      if (mod === 'campaign-trust') loadCampaignTrust();
      if (mod === 'rl-engine') loadRL();
      if (mod === 'simulation') loadSimulation();
    };
  });
}

async function refreshAll() {
  try {
    const [{ twins }, port] = await Promise.all([api('/api/twins'), api('/api/portfolio')]);
    STATE.twins = Object.fromEntries(twins.map(t => [t.customer_id, t]));
    STATE.portfolio = port;
    renderTopbar(port);
    renderKpis(port);
    renderRoster(twins);
    populateSelects(twins);
    if (!STATE.selected && twins.length) STATE.selected = twins[0].customer_id;
    if (STATE.selected) renderOverview(STATE.selected);
  } catch (e) {
    console.error('refresh failed', e);
  }
}

// ── Topbar ─────────────────────────────────────────────────────────────────
function renderTopbar(p) {
  $('#hdr-customers').textContent = p.customers ?? 0;
  $('#hdr-trust').textContent = fx(p.avg_trust ?? 0);
  $('#hdr-flagged').textContent = p.flagged ?? 0;
  $('#hdr-ltv').textContent = '$' + Math.round(p.total_ltv ?? 0).toLocaleString();
}

// ── KPI Strip ──────────────────────────────────────────────────────────────
function renderKpis(p) {
  const cards = [
    { lbl: 'CUSTOMERS', val: p.customers ?? 0, col: '--cyan' },
    { lbl: 'AVG TRUST', val: fx(p.avg_trust ?? 0), col: '--cyan' },
    { lbl: 'FLAGGED', val: p.flagged ?? 0, col: '--magenta' },
    { lbl: 'CAMPAIGN INTEGRITY', val: fx(p.campaign_integrity ?? 0), col: '--green' },
    { lbl: 'AVG PURCHASE INTENT', val: fx(p.avg_purchase_intent ?? 0), col: '--amber' },
    { lbl: 'PORTFOLIO LTV', val: '$' + Math.round(p.total_ltv ?? 0).toLocaleString(), col: '--cyan' },
  ];
  const colors = { '--cyan': '#00d4ff', '--magenta': '#ff2d6a', '--green': '#00ff88', '--amber': '#ffaa00' };
  $('#kpi-strip').innerHTML = cards.map(c => `
    <div class="kpi-card" style="--accent:${colors[c.col]}">
      <div class="kpi-lbl">${c.lbl}</div>
      <div class="kpi-val">${c.val}</div>
    </div>`).join('');
}

// ── Roster ─────────────────────────────────────────────────────────────────
function renderRoster(twins) {
  const order = { at_risk: 0, advocacy: 1, loyalty: 2, conversion: 3, consideration: 4, awareness: 5 };
  twins.sort((a, b) =>
    (b.trust.is_flagged - a.trust.is_flagged) ||
    ((order[a.journey_stage] ?? 9) - (order[b.journey_stage] ?? 9))
  );
  $('#roster-count').textContent = twins.length;
  $('#roster-list').innerHTML = twins.map(t => `
    <div class="roster-item ${t.customer_id === STATE.selected ? 'active' : ''}" data-id="${t.customer_id}">
      <span class="ri-dot" style="color:${trustColor(t.trust)};background:${trustColor(t.trust)}"></span>
      <div>
        <div class="ri-id">${t.customer_id}</div>
        <div class="ri-stage">${t.trust.is_flagged ? '⚠ FLAGGED' : t.journey_stage}</div>
      </div>
    </div>`).join('');
  $$('.roster-item').forEach(el => {
    el.onclick = () => {
      STATE.selected = el.dataset.id;
      renderRoster(Object.values(STATE.twins));
      renderOverview(STATE.selected);
    };
  });
}

// ── Populate Selects ───────────────────────────────────────────────────────
function populateSelects(twins) {
  const ids = twins.map(t => t.customer_id);
  const selects = ['#tl-customer-select', '#cf-customer-select', '#delib-customer-select', '#evo-customer-select'];
  selects.forEach(sel => {
    const el = $(sel);
    if (!el) return;
    const cur = el.value;
    el.innerHTML = ids.map(id => `<option value="${id}">${id}</option>`).join('');
    if (ids.includes(cur)) el.value = cur;
  });
}

// ── Overview Module ────────────────────────────────────────────────────────
async function renderOverview(id) {
  const t = STATE.twins[id];
  if (!t) return;
  $('#twin-id-label').textContent = id;

  // Twin Glyph
  $('#twin-core-display').innerHTML = twinGlyph(t) + twinMeta(t);

  // Emotion bars
  $('#emotion-bars-display').innerHTML = emotionBars(t);

  // Intent bars
  $('#intent-bars-display').innerHTML = intentBars(t);

  // NBA
  $('#nba-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>RUNNING AGENT GRAPH…</div>`;
  try {
    const d = await api(`/api/decide/${id}`, { method: 'POST' });
    $('#nba-display').innerHTML = renderNBA(d);
  } catch (e) {
    $('#nba-display').innerHTML = `<div class="empty-state">Decision engine unavailable</div>`;
  }
}

function twinGlyph(t) {
  const cx = 80, cy = 80;
  const arc = (r, frac, color, w = 7) => {
    const a = -Math.PI / 2;
    const b = a + frac * 2 * Math.PI;
    const x1 = cx + r * Math.cos(a), y1 = cy + r * Math.sin(a);
    const x2 = cx + r * Math.cos(b), y2 = cy + r * Math.sin(b);
    const large = frac > 0.5 ? 1 : 0;
    return `<path d="M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}" fill="none" stroke="${color}" stroke-width="${w}" stroke-linecap="round"/>`;
  };
  const ring = r => `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#0a1020" stroke-width="7"/>`;
  const valFrac = (t.emotion.valence + 1) / 2;
  return `<svg class="twin-glyph" width="160" height="160" viewBox="0 0 160 160">
    ${ring(68)}${ring(54)}${ring(40)}
    ${arc(68, t.trust.trust_score, t.trust.is_flagged ? '#ff2d6a' : '#00d4ff')}
    ${arc(54, valFrac, '#ffaa00')}
    ${arc(40, t.purchase_readiness, '#00ff88')}
    <text x="${cx}" y="${cy - 5}" text-anchor="middle" fill="#dde8ff" font-family="JetBrains Mono" font-size="18" font-weight="700">${pct(t.purchase_readiness)}</text>
    <text x="${cx}" y="${cy + 12}" text-anchor="middle" fill="#3d5080" font-family="JetBrains Mono" font-size="8">READINESS</text>
    <circle cx="${cx}" cy="${cy}" r="28" fill="rgba(0,212,255,0.04)" stroke="#1c2d52" stroke-width="1"/>
  </svg>`;
}

function twinMeta(t) {
  const rows = [
    ['STAGE', `<span class="tag-pill cyan">${t.journey_stage}</span>`],
    ['DOMINANT', `<span style="color:${EMO_COLOR[t.emotion.dominant]}">${t.emotion.dominant.replace(/_/g,' ')}</span>`],
    ['VALENCE / AROUSAL', `${fx(t.emotion.valence)} / ${fx(t.emotion.arousal)}`],
    ['VOLATILITY', fx(t.emotion.volatility)],
    ['TRUST SCORE', `<span style="color:${trustColor(t.trust)}">${fx(t.trust.trust_score)}</span>`],
    ['FRAUD PROB.', `<span style="color:${t.trust.fraud_probability > 0.5 ? '#ff2d6a' : '#7a90c0'}">${fx(t.trust.fraud_probability)}</span>`],
    ['LIFETIME VALUE', `<b>$${Math.round(t.lifetime_value).toLocaleString()}</b>`],
  ];
  return `<div class="twin-glyph-wrap"><svg class="twin-glyph" width="1" height="1"></svg><div class="twin-meta">${rows.map(([l, v]) => `<div class="twin-meta-row"><span class="tmr-lbl">${l}</span><span class="tmr-val">${v}</span></div>`).join('')}</div></div>`.replace('<svg class="twin-glyph" width="1" height="1"></svg>', twinGlyph(t));
}

function emotionBars(t) {
  return Object.entries(t.emotion.scores)
    .sort(([,a],[,b]) => b - a)
    .map(([k, v]) => `
      <div class="bar-row">
        <div class="bar-lbl">${k.replace(/_/g,' ')}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct(v)};background:${EMO_COLOR[k] ?? '#3d5080'}"></div></div>
        <div class="bar-val">${fx(v)}</div>
      </div>`).join('');
}

function intentBars(t) {
  const i = t.intent;
  return [
    ['purchase', i.purchase_intent, '#00d4ff'],
    ['churn', i.churn_intent, '#ff2d6a'],
    ['upsell', i.upsell_intent, '#00ff88'],
    ['engagement', i.engagement_intent, '#ffaa00'],
    ['support', i.support_intent, '#a855f7'],
    ['advocacy', i.advocacy_intent, '#00e5c8'],
    ['emotion shift risk', i.emotion_shift_risk, '#ff6820'],
    ['trust degradation', i.trust_degradation_risk, '#ff2d6a'],
  ].map(([l, v, c]) => `
    <div class="bar-row">
      <div class="bar-lbl">${l}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${pct(v)};background:${c}"></div></div>
      <div class="bar-val">${fx(v)}</div>
    </div>`).join('');
}

function renderNBA(d) {
  const hold = d.action === 'do_nothing';
  const attrs = Object.entries(d.feature_attributions);
  const maxA = Math.max(0.01, ...attrs.map(([,v]) => Math.abs(v)));
  const attrHtml = attrs.map(([k, v]) => {
    const w = (Math.abs(v) / maxA) * 48;
    const pos_neg = v >= 0 ? `<span class="attr-seg pos" style="width:${w}%"></span>` : `<span class="attr-seg neg" style="width:${w}%"></span>`;
    return `<div class="attr-row">
      <div class="attr-lbl">${k.replace(/_/g,' ')}</div>
      <div class="attr-meter"><div class="attr-center"></div>${pos_neg}</div>
    </div>`;
  }).join('');
  const traceHtml = d.agent_trace.map(s => `
    <div class="trace-step ${/trust gate|flagged/i.test(s.summary) ? 'gate' : ''}">
      <div class="trace-agent">${s.agent}</div>
      <div class="trace-sum">${s.summary}</div>
    </div>`).join('');
  return `
    <div class="nba-wrap">
      <div class="action-badge ${hold ? 'hold' : ''}">${d.action.replace(/_/g,' ')}</div>
      <div class="action-meta">via ${d.channel} · uplift <b style="color:${d.expected_uplift>=0?'#00ff88':'#ff2d6a'}">${d.expected_uplift>=0?'+':''}${fx(d.expected_uplift,3)}</b> · propensity ${fx(d.propensity)}</div>
      <div class="rationale-box">${d.rationale}</div>
      <div class="trace-grid">
        <div><div class="trace-section-lbl">AGENT TRACE (${d.agent_trace.length})</div>${traceHtml}</div>
        <div><div class="trace-section-lbl">FEATURE ATTRIBUTION (SHAP)</div><div class="attr">${attrHtml}</div></div>
      </div>
    </div>`;
}

// ============================================================================
//  MODULE 1: EMOTIONAL TWIN TIMELINE
// ============================================================================
async function loadTimeline() {
  const id = $('#tl-customer-select').value;
  if (!id) return;
  $('#timeline-chart-area').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>LOADING TIMELINE…</div>`;
  $('#timeline-summary').innerHTML = '';
  try {
    const data = await api(`/api/twin/${id}/timeline`);
    renderTimeline(data);
  } catch(e) {
    $('#timeline-chart-area').innerHTML = `<div class="empty-state">Failed to load timeline</div>`;
  }
}

function renderTimeline(data) {
  const points = data.timeline;
  const W = $('#timeline-chart-area').clientWidth - 32;
  const H = 280;
  const margin = { top: 20, right: 20, bottom: 30, left: 40 };
  const w = W - margin.left - margin.right;
  const h = H - margin.top - margin.bottom;

  const lines = [
    { key: 'valence', color: '#ffaa00', label: 'Valence', domain: [-1, 1] },
    { key: 'trust', color: '#00d4ff', label: 'Trust', domain: [0, 1] },
    { key: 'satisfaction', color: '#00ff88', label: 'Satisfaction', domain: [0, 1] },
    { key: 'volatility', color: '#ff2d6a', label: 'Volatility', domain: [0, 1] },
  ];

  const xScale = d => margin.left + (d.step / (points.length - 1)) * w;
  const yScale = (v, domain) => margin.top + (1 - (v - domain[0]) / (domain[1] - domain[0])) * h;

  const pathFor = (line) => {
    const pts = points.map(p => `${xScale(p)},${yScale(p[line.key], line.domain)}`);
    return 'M ' + pts.join(' L ');
  };

  const legendHtml = lines.map(l =>
    `<div class="tl-leg-item"><div class="tl-leg-line" style="background:${l.color}"></div><span>${l.label}</span></div>`
  ).join('');

  // Y axis ticks
  const yTicks = [-1, -0.5, 0, 0.5, 1];
  const yAxisHtml = yTicks.map(v =>
    `<line x1="${margin.left - 4}" x2="${margin.left}" y1="${yScale(v, [-1, 1])}" y2="${yScale(v, [-1, 1])}" stroke="#1c2d52" stroke-width="1"/>
     <text x="${margin.left - 8}" y="${yScale(v, [-1, 1]) + 4}" fill="#3d5080" font-family="JetBrains Mono" font-size="9" text-anchor="end">${v}</text>
     <line x1="${margin.left}" x2="${margin.left + w}" y1="${yScale(v, [-1, 1])}" y2="${yScale(v, [-1, 1])}" stroke="#0a1020" stroke-width="1" stroke-dasharray="4,4"/>`
  ).join('');

  const svgHtml = `
    <div class="tl-legend">${legendHtml}</div>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
      <rect x="${margin.left}" y="${margin.top}" width="${w}" height="${h}" fill="rgba(7,12,26,0.8)" rx="2"/>
      ${yAxisHtml}
      ${lines.map(l => `
        <path d="${pathFor(l)}" fill="none" stroke="${l.color}" stroke-width="1.5" stroke-linejoin="round" opacity="0.9"/>
        <path d="${pathFor(l)} L ${margin.left + w},${margin.top + h} L ${margin.left},${margin.top + h} Z" fill="${l.color}" opacity="0.04"/>
      `).join('')}
      <!-- drift bars -->
      ${points.filter(p => Math.abs(p.drift) > 0.02).map(p => `
        <rect x="${xScale(p) - 1}" y="${p.drift > 0 ? yScale(0.5, [-1,1]) : yScale(p.drift * 5, [-1,1])}" width="2" height="${Math.abs(p.drift) * 60}" fill="${p.drift > 0 ? '#00ff88' : '#ff2d6a'}" opacity="0.5"/>
      `).join('')}
    </svg>`;

  $('#timeline-chart-area').innerHTML = svgHtml;

  // Summary
  const s = data.summary;
  const trendColor = s.satisfaction_trend === 'improving' ? '#00ff88' : '#ff2d6a';
  const trustDeltaColor = s.trust_delta >= 0 ? '#00ff88' : '#ff2d6a';
  $('#timeline-summary').innerHTML = `
    <div class="tl-summary-card"><div class="tl-sc-lbl">TRUST DELTA</div><div class="tl-sc-val" style="color:${trustDeltaColor}">${pos(s.trust_delta)}</div></div>
    <div class="tl-summary-card"><div class="tl-sc-lbl">SATISFACTION TREND</div><div class="tl-sc-val" style="color:${trendColor}">${s.satisfaction_trend.toUpperCase()}</div></div>
    <div class="tl-summary-card"><div class="tl-sc-lbl">AVG VOLATILITY</div><div class="tl-sc-val" style="color:#ffaa00">${fx(s.emotion_volatility_avg)}</div></div>`;
}

// ============================================================================
//  MODULE 2: COUNTERFACTUAL JOURNEY SIMULATOR
// ============================================================================
async function loadCounterfactual() {
  const id = $('#cf-customer-select').value;
  if (!id) return;
  $('#cf-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>SIMULATING JOURNEYS…</div>`;
  try {
    const data = await api(`/api/twin/${id}/counterfactual`);
    renderCounterfactual(data);
  } catch(e) {
    $('#cf-display').innerHTML = `<div class="empty-state">Simulation failed</div>`;
  }
}

function renderCounterfactual(d) {
  const allScenarios = [d.actual, d.no_action_baseline, ...d.alternatives];
  const best = d.best_alternative;

  const scenarioCard = (s, extraClass = '', badge = '') => {
    const ltvColor = s.projected_ltv > 800 ? '#00ff88' : s.projected_ltv > 400 ? '#ffaa00' : '#ff2d6a';
    const deltaColor = s.delta_ltv >= 0 ? '#00ff88' : '#ff2d6a';
    return `
      <div class="cf-scenario ${extraClass}">
        ${badge ? `<div class="best-badge">${badge}</div>` : ''}
        <div class="cf-sc-label">${s.scenario.replace(/_/g,' ')}</div>
        <div class="cf-ltv" style="color:${ltvColor}">$${Math.round(s.projected_ltv).toLocaleString()}</div>
        <div class="cf-delta" style="color:${deltaColor}">${pos(s.delta_ltv)} LTV delta</div>
        <div class="cf-metric"><span class="cf-m-lbl">Trust Impact</span><span class="cf-m-val" style="color:${s.trust_impact>=0?'#00ff88':'#ff2d6a'}">${pos(s.trust_impact)}</span></div>
        <div class="cf-metric"><span class="cf-m-lbl">Churn Risk Δ</span><span class="cf-m-val" style="color:${s.churn_risk_delta>=0?'#ff2d6a':'#00ff88'}">${pos(s.churn_risk_delta)}</span></div>
        <div class="cf-metric"><span class="cf-m-lbl">Confidence</span><span class="cf-m-val">${pct(s.confidence)}</span></div>
      </div>`;
  };

  let html = `<div class="cf-grid">
    ${scenarioCard(d.actual, 'actual', 'ACTUAL')}
    ${scenarioCard(d.no_action_baseline, 'noaction', 'NO ACTION')}`;

  for (const alt of d.alternatives) {
    const isBest = alt.scenario === best;
    html += scenarioCard(alt, isBest ? 'best' : '', isBest ? 'BEST ALT' : '');
  }
  html += '</div>';

  // Comparison chart
  const allLtv = allScenarios.map(s => s.projected_ltv);
  const maxLtv = Math.max(...allLtv);
  html += `
    <div style="background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:16px;">
      <div class="sim-chart-title">PROJECTED LTV COMPARISON</div>
      <div class="sim-bar-group">
        ${allScenarios.map(s => {
          const pct_w = ((s.projected_ltv / maxLtv) * 100).toFixed(1);
          const color = s.scenario === 'actual_path' ? '#00d4ff' : s.scenario === 'no_action_baseline' ? '#ff2d6a' : s.scenario === best ? '#00ff88' : '#7a90c0';
          return `<div class="sim-bar-item">
            <div class="sim-bar-name">${s.scenario.replace(/_/g,' ')}</div>
            <div class="sim-bar-track"><div class="sim-bar-fill" style="width:${pct_w}%;background:${color}">$${Math.round(s.projected_ltv).toLocaleString()}</div></div>
          </div>`;
        }).join('')}
      </div>
    </div>`;

  $('#cf-display').innerHTML = html;
}

// ============================================================================
//  MODULE 3: NEO4J KNOWLEDGE GRAPH (D3 Force)
// ============================================================================
async function loadKnowledgeGraph() {
  $('#kg-info').textContent = 'Loading graph…';
  try {
    const data = await api('/api/knowledge-graph');
    // Defensive: drop any edge that references a node id not present in
    // the node set, since d3-force throws and aborts the whole render
    // if a single link points at a missing node.
    const ids = new Set(data.nodes.map(n => n.id));
    data.edges = data.edges.filter(e => ids.has(e.source) && ids.has(e.target));
    renderKnowledgeGraph(data);
  } catch(e) {
    console.error('knowledge-graph render failed:', e);
    $('#kg-info').textContent = 'Graph unavailable';
  }
}

function renderKnowledgeGraph(data) {
  const svg = d3.select('#kg-svg');
  svg.selectAll('*').remove();
  const W = svg.node().parentElement.clientWidth;
  const H = 580;
  svg.attr('width', W).attr('height', H);

  const nodeColor = type => ({
    customer: '#00d4ff', emotion: '#ffaa00', campaign: '#a855f7',
    channel: '#00ff88', product: '#ff6820'
  })[type] || '#7a90c0';

  const nodeR = type => ({ customer: 12, emotion: 9, campaign: 11, channel: 8, product: 9 })[type] || 8;

  const simulation = d3.forceSimulation(data.nodes)
    .force('link', d3.forceLink(data.edges).id(d => d.id).distance(90).strength(0.4))
    .force('charge', d3.forceManyBody().strength(-180))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(d => nodeR(d.type) + 8));

  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.3, 3]).on('zoom', e => g.attr('transform', e.transform)));

  // Defs - glow filter
  const defs = svg.append('defs');
  defs.append('filter').attr('id', 'glow')
    .append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'coloredBlur');

  const link = g.selectAll('.kg-link')
    .data(data.edges).enter().append('line')
    .attr('class', 'kg-link')
    .attr('stroke', d => `rgba(${d.rel === 'feels' ? '255,170,0' : '28,45,82'}, 0.6)`)
    .attr('stroke-width', d => Math.max(0.5, (d.weight ?? 0.5) * 2))
    .attr('stroke-dasharray', d => d.rel === 'exposed_to' ? '4,3' : 'none');

  const linkLabel = g.selectAll('.kg-link-label')
    .data(data.edges).enter().append('text')
    .attr('fill', '#253660')
    .attr('font-family', 'JetBrains Mono')
    .attr('font-size', '7')
    .text(d => d.rel.replace(/_/g,' '));

  const nodeG = g.selectAll('.kg-node')
    .data(data.nodes).enter().append('g')
    .attr('class', 'kg-node')
    .style('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end', (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  nodeG.append('circle')
    .attr('r', d => nodeR(d.type))
    .attr('fill', d => nodeColor(d.type))
    .attr('fill-opacity', 0.2)
    .attr('stroke', d => nodeColor(d.type))
    .attr('stroke-width', d => d.flagged ? 2.5 : 1.5)
    .attr('stroke-dasharray', d => d.flagged ? '3,2' : 'none');

  nodeG.append('circle')
    .attr('r', d => nodeR(d.type) * 0.4)
    .attr('fill', d => nodeColor(d.type))
    .attr('fill-opacity', 0.8);

  nodeG.append('text')
    .attr('dy', d => nodeR(d.type) + 10)
    .attr('text-anchor', 'middle')
    .attr('fill', '#7a90c0')
    .attr('font-family', 'JetBrains Mono')
    .attr('font-size', d => d.type === 'customer' ? '8' : '7')
    .text(d => d.label.length > 12 ? d.label.slice(0, 12) + '…' : d.label);

  // Tooltip
  let tooltip = document.querySelector('.kg-tooltip');
  if (!tooltip) { tooltip = document.createElement('div'); tooltip.className = 'kg-tooltip'; document.body.appendChild(tooltip); }

  nodeG.on('mouseover', (e, d) => {
    const lines = [`TYPE: ${d.type}`, `ID: ${d.label}`];
    if (d.trust !== undefined) lines.push(`TRUST: ${fx(d.trust)}`);
    if (d.stage) lines.push(`STAGE: ${d.stage}`);
    if (d.ltv) lines.push(`LTV: $${Math.round(d.ltv)}`);
    if (d.emotion) lines.push(`EMOTION: ${d.emotion}`);
    if (d.flagged) lines.push('⚠ FLAGGED');
    tooltip.textContent = lines.join('\n');
    tooltip.style.display = 'block';
  })
  .on('mousemove', e => {
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top = (e.clientY - 14) + 'px';
  })
  .on('mouseout', () => { tooltip.style.display = 'none'; });

  simulation.on('tick', () => {
    link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
    linkLabel.attr('x', d => (d.source.x + d.target.x) / 2).attr('y', d => (d.source.y + d.target.y) / 2);
    nodeG.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  $('#kg-info').textContent = `${data.nodes.length} nodes · ${data.edges.length} edges · Drag to rearrange · Scroll to zoom`;
}

// ============================================================================
//  MODULE 4: MULTI-AGENT DELIBERATION CONSOLE
// ============================================================================
async function loadDeliberation() {
  const id = $('#delib-customer-select').value;
  if (!id) return;
  $('#delib-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>RUNNING DELIBERATION…</div>`;
  try {
    const data = await api(`/api/twin/${id}/deliberation`);
    renderDeliberation(data);
  } catch(e) {
    $('#delib-display').innerHTML = `<div class="empty-state">Deliberation unavailable</div>`;
  }
}

function renderDeliberation(d) {
  const rounds = {};
  d.deliberation_rounds.forEach(r => {
    if (!rounds[r.round]) rounds[r.round] = [];
    rounds[r.round].push(r);
  });

  let timeline = '';
  for (const [round, agents] of Object.entries(rounds)) {
    timeline += `<div class="delib-round-label">ROUND ${round} — DELIBERATION</div>`;
    for (const a of agents) {
      const isGate = a.is_gate;
      const gateClass = isGate ? (a.gate_pass ? 'gate-pass' : 'gate') : '';
      timeline += `
        <div class="delib-agent-card ${gateClass}">
          <div class="dac-agent">${a.agent}</div>
          <div class="dac-body">
            <div class="dac-proposal">${a.proposal}</div>
            <div class="dac-votes">
              <span class="vote-chip agree">✓ ${a.votes.agree} AGREE</span>
              <span class="vote-chip disagree">✗ ${a.votes.disagree} DISAGREE</span>
            </div>
            <div class="conf-bar"><div class="conf-fill" style="width:${pct(a.confidence)}"></div></div>
          </div>
        </div>`;
    }
  }

  const summary = `
    <div class="delib-summary">
      <div class="consensus-ring">
        <div class="consensus-score">${(d.consensus_score * 100).toFixed(0)}<span style="font-size:16px">%</span></div>
        <div class="consensus-lbl">CONSENSUS SCORE</div>
      </div>
      <div class="final-action-box">
        <div class="fa-val">${d.final_action.replace(/_/g,' ')}</div>
        <div class="fa-lbl">FINAL ACTION</div>
        <div style="margin-top:6px"><div class="fa-val" style="font-size:11px">${d.final_channel}</div><div class="fa-lbl">CHANNEL</div></div>
      </div>
      <div style="margin-top:12px;font-size:10.5px;color:var(--ink-faint);line-height:1.6">${d.rationale}</div>
    </div>`;

  $('#delib-display').innerHTML = `<div class="delib-grid"><div class="delib-timeline">${timeline}</div>${summary}</div>`;
}

// ============================================================================
//  MODULE 5: CAMPAIGN TRUST GRAPH
// ============================================================================
async function loadCampaignTrust() {
  $('#ct-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>LOADING CAMPAIGN TRUST GRAPH…</div>`;
  try {
    const data = await api('/api/campaign-trust-graph');
    renderCampaignTrust(data);
  } catch(e) {
    $('#ct-display').innerHTML = `<div class="empty-state">Graph unavailable</div>`;
  }
}

function renderCampaignTrust(d) {
  const integrityClass = i => i > 0.8 ? 'high' : i > 0.6 ? 'medium' : 'low';
  const integrityColor = i => i > 0.8 ? '#00ff88' : i > 0.6 ? '#ffaa00' : '#ff2d6a';

  const campaignCards = d.campaigns.map(c => {
    const cls = integrityClass(c.integrity);
    const col = integrityColor(c.integrity);
    return `
      <div class="ct-campaign-card ${cls}">
        <div class="ct-camp-name">${c.name}</div>
        <div style="float:right;margin:0 0 10px 10px;">
          <svg width="60" height="60" viewBox="0 0 60 60">
            <circle cx="30" cy="30" r="24" fill="none" stroke="#0a1020" stroke-width="6"/>
            <circle cx="30" cy="30" r="24" fill="none" stroke="${col}" stroke-width="6"
              stroke-dasharray="${c.integrity * 150.8} 150.8" stroke-linecap="round"
              transform="rotate(-90 30 30)" opacity="0.9"/>
            <text x="30" y="34" text-anchor="middle" fill="${col}" font-family="JetBrains Mono" font-size="11" font-weight="700">${(c.integrity * 100).toFixed(0)}%</text>
          </svg>
        </div>
        <div class="ct-metric"><span style="color:var(--ink-faint)">REACH</span><span style="font-family:var(--mono)">${c.reach.toLocaleString()}</span></div>
        <div class="ct-metric"><span style="color:var(--ink-faint)">BOT RATE</span><span style="font-family:var(--mono);color:${c.bot_rate > 0.2 ? '#ff2d6a' : '#00ff88'}">${(c.bot_rate * 100).toFixed(1)}%</span></div>
        <div class="ct-metric"><span style="color:var(--ink-faint)">INTEGRITY</span><span style="font-family:var(--mono);color:${col}">${(c.integrity * 100).toFixed(1)}%</span></div>
        <div style="clear:both"></div>
      </div>`;
  }).join('');

  const tableRows = d.customer_clusters.map(c => `
    <div class="ct-table-row ${c.is_flagged ? 'flagged' : ''}">
      <div style="font-family:var(--mono)">${c.customer_id}</div>
      <div style="font-family:var(--mono);color:var(--ink-faint)">${c.campaign}</div>
      <div style="font-family:var(--mono);color:${c.fraud_probability > 0.5 ? '#ff2d6a' : '#00ff88'}">${fx(c.fraud_probability)}</div>
      <div style="font-family:var(--mono);color:${c.bot_score > 0.5 ? '#ff2d6a' : '#7a90c0'}">${fx(c.bot_score)}</div>
      <div>${c.is_flagged ? '<span class="flag-indicator">⚠ FLAGGED</span>' : '<span class="ok-indicator">✓ OK</span>'}</div>
    </div>`).join('');

  $('#ct-display').innerHTML = `
    <div class="ct-grid">${campaignCards}</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
      <div class="ov-panel">
        <div class="panel-label">SUSPICIOUS CLUSTERS</div>
        <div style="font-family:var(--mono);font-size:28px;font-weight:700;color:#ff2d6a">${d.suspicious_cluster_count}</div>
        <div style="font-family:var(--mono);font-size:9px;color:var(--ink-faint)">CUSTOMERS WITH FRAUD PROB > 50%</div>
      </div>
      <div class="ov-panel">
        <div class="panel-label">GLOBAL BOT RATE</div>
        <div style="font-family:var(--mono);font-size:28px;font-weight:700;color:${d.global_bot_rate > 0.2 ? '#ff2d6a' : '#ffaa00'}">${(d.global_bot_rate * 100).toFixed(1)}%</div>
        <div style="font-family:var(--mono);font-size:9px;color:var(--ink-faint)">ACROSS ALL CAMPAIGNS</div>
      </div>
    </div>
    <div class="ct-cluster-table">
      <div class="ct-table-header"><span>CUSTOMER</span><span>CAMPAIGN</span><span>FRAUD PROB</span><span>BOT SCORE</span><span>STATUS</span></div>
      ${tableRows}
    </div>`;
}

// ============================================================================
//  MODULE 6: AFFECTIVE RL ENGINE
// ============================================================================
async function loadRL() {
  $('#rl-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>LOADING RL STATE…</div>`;
  try {
    const data = await api('/api/rl-state');
    renderRL(data);
  } catch(e) {
    $('#rl-display').innerHTML = `<div class="empty-state">RL state unavailable</div>`;
  }
}

function renderRL(data) {
  const episodes = data.episodes.slice(-15); // show last 15
  const weights = data.reward_weights;

  // Weight bars
  const wColors = { revenue: '#00d4ff', retention: '#00ff88', trust: '#00e5c8', emotional_satisfaction: '#ffaa00', ltv: '#a855f7' };
  const weightsHtml = Object.entries(weights).map(([k, v]) => `
    <div class="rw-item">
      <div class="rw-label">${k.replace(/_/g,' ')}</div>
      <div class="rw-bar"><div class="rw-fill" style="width:${(v*100).toFixed(0)}%;background:${wColors[k] ?? '#7a90c0'}"></div></div>
      <div class="rw-pct">${(v*100).toFixed(0)}%</div>
    </div>`).join('');

  // Chart: cumulative reward
  const W = 600; const H = 180;
  const margin = { top: 14, right: 14, bottom: 24, left: 50 };
  const cw = W - margin.left - margin.right;
  const ch = H - margin.top - margin.bottom;
  const maxR = Math.max(...episodes.map(e => e.cumulative_reward));
  const minR = Math.min(...episodes.map(e => e.cumulative_reward));
  const xs = i => margin.left + (i / (episodes.length - 1)) * cw;
  const ys = v => margin.top + (1 - (v - minR) / (maxR - minR || 1)) * ch;
  const curvePts = episodes.map((e, i) => `${xs(i)},${ys(e.cumulative_reward)}`).join(' L ');
  const rewardPts = episodes.map((e, i) => `${xs(i)},${ys(e.total_reward)}`).join(' L ');

  const chartSvg = `
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
      <rect x="${margin.left}" y="${margin.top}" width="${cw}" height="${ch}" fill="rgba(7,12,26,0.7)" rx="2"/>
      ${[0.25, 0.5, 0.75, 1].map(f => {
        const yv = margin.top + (1 - f) * ch;
        return `<line x1="${margin.left}" x2="${margin.left+cw}" y1="${yv}" y2="${yv}" stroke="#0a1020" stroke-width="1"/>
                <text x="${margin.left-6}" y="${yv+3}" fill="#3d5080" font-family="JetBrains Mono" font-size="8" text-anchor="end">${Math.round(minR + f*(maxR-minR))}</text>`;
      }).join('')}
      <path d="M ${rewardPts}" fill="none" stroke="#ffaa00" stroke-width="1.5" opacity="0.7"/>
      <path d="M ${curvePts}" fill="none" stroke="#00d4ff" stroke-width="2"/>
      <path d="M ${curvePts} L ${xs(episodes.length-1)},${margin.top+ch} L ${margin.left},${margin.top+ch} Z" fill="#00d4ff" opacity="0.05"/>
      ${episodes.map((e, i) => `<circle cx="${xs(i)}" cy="${ys(e.cumulative_reward)}" r="2.5" fill="#00d4ff" opacity="0.8"/>`).join('')}
      <text x="${margin.left+cw}" y="${margin.top-4}" fill="#00d4ff" font-family="JetBrains Mono" font-size="8" text-anchor="end">CUMULATIVE REWARD</text>
      <text x="${margin.left+cw}" y="${margin.top+8}" fill="#ffaa00" font-family="JetBrains Mono" font-size="8" text-anchor="end">EPISODE REWARD</text>
    </svg>`;

  // Episode table (last 8)
  const tableRows = data.episodes.slice(-8).map(e => `
    <div class="rl-trow">
      <div>${e.episode}</div>
      <div class="${e.revenue_reward >= 0 ? 'pos-reward' : 'neg-reward'}">${fx(e.revenue_reward)}</div>
      <div class="${e.retention_reward >= 0 ? 'pos-reward' : 'neg-reward'}">${fx(e.retention_reward)}</div>
      <div class="${e.trust_reward >= 0 ? 'pos-reward' : 'neg-reward'}">${fx(e.trust_reward)}</div>
      <div class="${e.emotional_satisfaction_reward >= 0 ? 'pos-reward' : 'neg-reward'}">${fx(e.emotional_satisfaction_reward)}</div>
      <div class="${e.ltv_reward >= 0 ? 'pos-reward' : 'neg-reward'}">${fx(e.ltv_reward)}</div>
      <div style="color:#00d4ff;font-weight:600">${fx(e.total_reward)}</div>
    </div>`).join('');

  $('#rl-display').innerHTML = `
    <div class="rl-top">
      <div id="rl-chart-area">
        <div class="sim-chart-title">CUMULATIVE REWARD TRAJECTORY</div>
        ${chartSvg}
      </div>
      <div class="rl-weights">
        <div class="rw-title">REWARD WEIGHTS</div>
        ${weightsHtml}
      </div>
    </div>
    <div class="rl-episode-table">
      <div class="rl-thead"><span>EP</span><span>REVENUE</span><span>RETENTION</span><span>TRUST</span><span>EMO SAT</span><span>LTV</span><span>TOTAL</span></div>
      ${tableRows}
    </div>`;
}

// ============================================================================
//  MODULE 7: DIGITAL TWIN SIMULATION SANDBOX
// ============================================================================
async function loadSimulation() {
  $('#sim-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>RUNNING 500 SYNTHETIC TWINS…</div>`;
  try {
    const data = await api('/api/simulation/sandbox');
    renderSimulation(data);
  } catch(e) {
    $('#sim-display').innerHTML = `<div class="empty-state">Simulation failed</div>`;
  }
}

function renderSimulation(data) {
  const results = data.results;
  const camps = Object.entries(results);
  const bestCamp = camps.reduce((a, b) => (b[1].avg_ltv_delta > a[1].avg_ltv_delta ? b : a));

  const cards = camps.map(([name, r]) => {
    const isBest = name === bestCamp[0];
    const convColor = r.conversion_rate > 0.25 ? '#00ff88' : r.conversion_rate > 0.15 ? '#ffaa00' : '#ff2d6a';
    return `
      <div class="sim-camp-card ${isBest ? 'best-sim' : ''}">
        ${isBest ? '<div class="best-badge">RECOMMENDED</div>' : ''}
        <div class="sim-camp-name">${name.replace(/_/g,' ')}</div>
        <div class="sim-conv-rate" style="color:${convColor}">${(r.conversion_rate * 100).toFixed(1)}<span style="font-size:12px">%</span></div>
        <div class="sim-lbl-small">CONVERSION RATE · ${data.n_twins} TWINS</div>
        <div class="sim-metric"><span style="color:var(--ink-faint)">AVG LTV Δ</span><span style="font-family:var(--mono);color:${r.avg_ltv_delta>=0?'#00ff88':'#ff2d6a'}">${pos(r.avg_ltv_delta)}</span></div>
        <div class="sim-metric"><span style="color:var(--ink-faint)">TRUST Δ</span><span style="font-family:var(--mono);color:${r.avg_trust_delta>=0?'#00ff88':'#ff2d6a'}">${pos(r.avg_trust_delta)}</span></div>
        <div class="sim-metric"><span style="color:var(--ink-faint)">CHURN RATE</span><span style="font-family:var(--mono);color:${r.churn_rate>0.1?'#ff2d6a':'#00ff88'}">${(r.churn_rate*100).toFixed(1)}%</span></div>
        <div class="sim-metric"><span style="color:var(--ink-faint)">EXP REVENUE</span><span style="font-family:var(--mono)">${pos(r.expected_revenue)}</span></div>
      </div>`;
  }).join('');

  // Horizontal comparison chart
  const maxConv = Math.max(...camps.map(([,r]) => r.conversion_rate));
  const compChart = `
    <div class="sim-comparison-chart">
      <div class="sim-chart-title">CONVERSION RATE COMPARISON · ${data.n_twins} SYNTHETIC TWINS PER CAMPAIGN</div>
      <div class="sim-bar-group">
        ${camps.map(([name, r]) => {
          const pct_w = (r.conversion_rate / maxConv * 100).toFixed(1);
          const color = name === bestCamp[0] ? '#00ff88' : '#00d4ff';
          return `<div class="sim-bar-item">
            <div class="sim-bar-name">${name.replace(/_/g,' ')}</div>
            <div class="sim-bar-track"><div class="sim-bar-fill" style="width:${pct_w}%;background:${color}">${(r.conversion_rate*100).toFixed(1)}%</div></div>
          </div>`;
        }).join('')}
      </div>
    </div>`;

  $('#sim-display').innerHTML = `<div class="sim-header-grid">${cards}</div>${compChart}`;
}

// ============================================================================
//  MODULE 8: TWIN EVOLUTION ENGINE
// ============================================================================
async function loadEvolution() {
  const id = $('#evo-customer-select').value;
  if (!id) return;
  $('#evo-display').innerHTML = `<div class="loading-state"><div class="loading-spinner"></div>LOADING EVOLUTION ENGINE…</div>`;
  try {
    const data = await api(`/api/twin/${id}/evolution`);
    renderEvolution(data);
  } catch(e) {
    $('#evo-display').innerHTML = `<div class="empty-state">Evolution data unavailable</div>`;
  }
}

function renderEvolution(data) {
  const ev = data.evolution;
  const cur = data.current;

  const stateCards = [
    { lbl: 'EMOTIONAL STATE', val: cur.emotional_state, color: '#ffaa00', domain: [-1, 1] },
    { lbl: 'TRUST STATE', val: cur.trust_state, color: '#00d4ff', domain: [0, 1] },
    { lbl: 'INTENT STATE', val: cur.intent_state, color: '#00ff88', domain: [0, 1] },
    { lbl: 'BEHAVIORAL STATE', val: cur.behavioral_state, color: '#a855f7', domain: [0, 1] },
  ];

  const stateHtml = stateCards.map(s => `
    <div class="evo-state-card">
      <div class="esc-lbl">${s.lbl}</div>
      <div class="esc-val" style="color:${s.color}">${fx(s.val)}</div>
    </div>`).join('');

  // Chart
  const W = 700; const H = 220;
  const margin = { top: 14, right: 14, bottom: 24, left: 44 };
  const cw = W - margin.left - margin.right;
  const ch = H - margin.top - margin.bottom;

  const chartLines = [
    { key: 'emotional_state', color: '#ffaa00', domain: [-1, 1] },
    { key: 'trust_state', color: '#00d4ff', domain: [0, 1] },
    { key: 'intent_state', color: '#00ff88', domain: [0, 1] },
    { key: 'behavioral_state', color: '#a855f7', domain: [0, 1] },
  ];
  const xs = i => margin.left + (i / (ev.length - 1)) * cw;
  const ys = (v, d) => margin.top + (1 - (v - d[0]) / (d[1] - d[0])) * ch;

  const gridLines = [0, 0.5, 1].map(f =>
    `<line x1="${margin.left}" x2="${margin.left+cw}" y1="${margin.top + (1-f)*ch}" y2="${margin.top + (1-f)*ch}" stroke="#0a1020" stroke-width="1"/>
     <text x="${margin.left-5}" y="${margin.top + (1-f)*ch + 4}" fill="#3d5080" font-family="JetBrains Mono" font-size="8" text-anchor="end">${f}</text>`
  ).join('');

  const pathLines = chartLines.map(l => {
    const pts = ev.map((e, i) => `${xs(i)},${ys(e[l.key], l.domain)}`).join(' L ');
    return `<path d="M ${pts}" fill="none" stroke="${l.color}" stroke-width="1.5" opacity="0.85"/>`;
  }).join('');

  // Animated scanning line
  const scanLine = `
    <line id="evo-scan" x1="${margin.left + cw}" x2="${margin.left + cw}" y1="${margin.top}" y2="${margin.top + ch}" stroke="rgba(0,212,255,0.4)" stroke-width="1"/>`;

  const legend = chartLines.map(l =>
    `<div class="tl-leg-item"><div class="tl-leg-line" style="background:${l.color}"></div><span>${l.key.replace(/_/g,' ')}</span></div>`
  ).join('');

  const chartSvg = `
    <div class="tl-legend">${legend}</div>
    <svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">
      <rect x="${margin.left}" y="${margin.top}" width="${cw}" height="${ch}" fill="rgba(7,12,26,0.8)" rx="2"/>
      ${gridLines}
      ${pathLines}
      ${scanLine}
      <text x="${margin.left}" y="${margin.top - 4}" fill="#3d5080" font-family="JetBrains Mono" font-size="8">T-24H</text>
      <text x="${margin.left + cw}" y="${margin.top - 4}" fill="#00d4ff" font-family="JetBrains Mono" font-size="8" text-anchor="end">NOW</text>
    </svg>`;

  $('#evo-display').innerHTML = `
    <div class="evo-state-grid">${stateHtml}</div>
    <div style="margin-bottom:12px;font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;color:var(--ink-faint)">24-HOUR TWIN STATE EVOLUTION · ${data.customer_id}</div>
    ${chartSvg}
    <div style="margin-top:12px;display:grid;grid-template-columns:repeat(4,1fr);gap:8px">
      ${chartLines.map(l => {
        const vals = ev.map(e => e[l.key]);
        const min = Math.min(...vals), max = Math.max(...vals);
        const last = vals[vals.length - 1];
        const first = vals[0];
        const delta = last - first;
        return `<div class="ov-panel">
          <div class="panel-label">${l.key.replace(/_/g,' ')}</div>
          <div style="font-family:var(--mono);font-size:16px;font-weight:700;color:${l.color}">${fx(last)}</div>
          <div style="font-family:var(--mono);font-size:9px;color:${delta>=0?'#00ff88':'#ff2d6a'};margin-top:2px">${pos(delta)} 24H</div>
          <div style="font-family:var(--mono);font-size:8px;color:var(--ink-faint);margin-top:4px">MIN ${fx(min)} · MAX ${fx(max)}</div>
        </div>`;
      }).join('')}
    </div>`;
}

// ── Launch ─────────────────────────────────────────────────────────────────
boot();
