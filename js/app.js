import { MAP_PATHS } from './map-data.js';

/* ============================================================
   State
   ============================================================ */
const state = {
  lang: 'en',
  data: { parties: {}, cantons: {}, initiatives: [], i18n: {}, financing: { parties: {}, initiatives: {} } },
  filter: 'all',
  search: ''
};

const SUPPORTED_LANGS = ['en', 'de', 'fr', 'it'];

/* ============================================================
   Data loading
   ============================================================ */
async function loadData() {
  const [parties, cantons, initiatives, i18n] = await Promise.all([
    fetch('data/parties.json').then(r => r.json()),
    fetch('data/cantons.json').then(r => r.json()),
    fetch('data/initiatives.json').then(r => r.json()),
    fetch('data/i18n.json').then(r => r.json())
  ]);
  state.data.parties = parties.parties;
  state.data.cantons = cantons.cantons;
  state.data.initiatives = initiatives.initiatives;
  state.data.i18n = i18n;

  // Optional: fetched at build time from the official EFK register (see
  // scripts/fetch_financing.py). Missing file or fetch failure just means
  // no live figures yet — pages fall back to the "see official register" copy.
  try {
    const financing = await fetch('data/financing.json').then(r => r.ok ? r.json() : null);
    if (financing) state.data.financing = financing;
  } catch (e) { /* keep the empty default; placeholders will show */ }
}

/* ============================================================
   i18n helpers
   ============================================================ */
function t(key) {
  const dict = state.data.i18n[state.lang] || state.data.i18n.en || {};
  return dict[key] ?? state.data.i18n.en?.[key] ?? key;
}
function localized(obj) {
  if (!obj) return '';
  return obj[state.lang] || obj.en || Object.values(obj)[0] || '';
}

/* ============================================================
   Financing (from data/financing.json, fetched at build time
   from the official EFK register — see scripts/fetch_financing.py)
   ============================================================ */
const CHF_LOCALES = { en: 'en-CH', de: 'de-CH', fr: 'fr-CH', it: 'it-CH' };
function formatCHF(n) {
  const locale = CHF_LOCALES[state.lang] || 'en-CH';
  return new Intl.NumberFormat(locale, { maximumFractionDigits: 0 }).format(n || 0) + ' CHF';
}

function renderDonorList(donors) {
  if (!donors || donors.length === 0) {
    return `<p class="detail-source">${t('financing.noDonors')}</p>`;
  }
  return `
    <div class="detail-facts">
      ${donors.map(d => `
        <div class="detail-fact">
          <strong>${d.name}${d.location ? ` (${d.location})` : ''}</strong>
          <span>${formatCHF(d.amount)}${d.date ? ` — ${d.date}` : ''}</span>
        </div>`).join('')}
    </div>`;
}

function renderFinancingSource() {
  const meta = state.data.financing._meta;
  const date = meta?.fetchedAt ? meta.fetchedAt.slice(0, 10) : '';
  return `<p class="detail-source">${t('financing.source').replace('{date}', date)}</p>`;
}

function applyStaticTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.innerHTML = t(el.getAttribute('data-i18n'));
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.setAttribute('placeholder', t(el.getAttribute('data-i18n-ph')));
  });
  document.documentElement.lang = state.lang;
}

function setLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en';
  state.lang = lang;
  try { localStorage.setItem('politikch-lang', lang); } catch (e) { /* ignore */ }
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
    b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false');
  });
  applyStaticTranslations();
  renderInitiatives();
  // Re-render an open subpage so its content follows the language
  const route = parseHash();
  if (route.view === 'canton') renderCantonPage(route.id);
  if (route.view === 'party') renderPartyPage(route.id);
  if (route.view === 'initiative') renderInitiativePage(route.id);
}

/* ============================================================
   Hemicycle
   ============================================================ */
function renderHemicycle(containerId, seatData, totalSeats) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  const cx = 200, cy = 190, rInner = 62;

  // Reference geometry is tuned for a 200-seat chamber. Smaller chambers get
  // fewer rows and a smaller radius so seat spacing stays consistent instead
  // of stretching a handful of seats across the full arc.
  const refSeats = 200, rowsRef = 6, rOuterRef = 178;
  const seatCount = Object.values(seatData).reduce((a, b) => a + b, 0);
  const fill = Math.min(1, seatCount / refSeats);
  const rows = Math.max(1, Math.round(rowsRef * Math.sqrt(fill)));
  const rOuter = Math.sqrt(rInner * rInner + (rOuterRef * rOuterRef - rInner * rInner) * fill);

  // Parties ordered left-to-right by political position (spectrum.x)
  const orderedParties = Object.entries(seatData)
    .sort((a, b) => (state.data.parties[a[0]]?.spectrum?.x ?? 50) - (state.data.parties[b[0]]?.spectrum?.x ?? 50));

  const rowRadii = [];
  for (let r = 0; r < rows; r++) rowRadii.push(rows === 1 ? rOuter : rInner + (rOuter - rInner) * (r / (rows - 1)));
  const totalLen = rowRadii.reduce((s, r) => s + r, 0);
  const rowWeights = rowRadii.map(r => r / totalLen);

  // Give each party a share of every row (proportional to row length), so a
  // party's seats form one radial wedge instead of being siloed in one row.
  const perPartyRowCounts = orderedParties.map(([, n]) => {
    const counts = rowWeights.map(w => Math.round(w * n));
    let drift = n - counts.reduce((a, b) => a + b, 0);
    let ri = counts.length - 1;
    while (drift !== 0) {
      counts[ri] += drift > 0 ? 1 : -1;
      drift += drift > 0 ? -1 : 1;
      ri = (ri - 1 + counts.length) % counts.length;
    }
    return counts;
  });

  const rowSeatLists = rowRadii.map((_, row) => {
    const list = [];
    orderedParties.forEach(([key], p) => {
      const color = state.data.parties[key]?.color || '#999';
      for (let i = 0; i < perPartyRowCounts[p][row]; i++) list.push({ party: key, color });
    });
    return list;
  });

  const svgNS = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('viewBox', '0 0 400 205');
  svg.setAttribute('role', 'img');
  svg.setAttribute('aria-label', `${totalSeats} seats by party`);

  rowRadii.forEach((radius, row) => {
    const list = rowSeatLists[row];
    const count = list.length;
    for (let i = 0; i < count; i++) {
      const angle = Math.PI + (count === 1 ? 0.5 : i / (count - 1)) * Math.PI;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      const s = list[i];
      const circle = document.createElementNS(svgNS, 'circle');
      circle.setAttribute('cx', x.toFixed(1));
      circle.setAttribute('cy', y.toFixed(1));
      circle.setAttribute('r', '4.6');
      circle.setAttribute('fill', s.color);
      circle.setAttribute('opacity', '0.92');
      circle.setAttribute('tabindex', '0');
      circle.setAttribute('role', 'button');
      circle.style.cursor = 'pointer';
      circle.style.transition = 'r 0.15s, opacity 0.15s';
      const label = `${state.data.parties[s.party]?.abbr || s.party}`;
      circle.setAttribute('aria-label', label);
      const enter = () => { circle.setAttribute('r', '6.6'); circle.setAttribute('opacity', '1'); };
      const leave = () => { circle.setAttribute('r', '4.6'); circle.setAttribute('opacity', '0.92'); };
      circle.addEventListener('mouseenter', enter);
      circle.addEventListener('mouseleave', leave);
      circle.addEventListener('focus', enter);
      circle.addEventListener('blur', leave);
      circle.addEventListener('click', () => navigate(`party/${s.party}`));
      circle.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`party/${s.party}`); } });
      svg.appendChild(circle);
    }
  });

  container.appendChild(svg);
  const total = document.createElement('div');
  total.className = 'hemicycle-total';
  total.innerHTML = `<div class="num">${totalSeats}</div><div class="lbl">seats</div>`;
  container.appendChild(total);
}

function renderLegend(containerId, seatData) {
  const container = document.getElementById(containerId);
  container.innerHTML = '';
  Object.entries(seatData)
    .sort((a, b) => (state.data.parties[a[0]]?.spectrum?.x ?? 50) - (state.data.parties[b[0]]?.spectrum?.x ?? 50))
    .forEach(([key, seats]) => {
      const p = state.data.parties[key];
      if (!p) return;
      const item = document.createElement('button');
      item.className = 'legend-item';
      item.type = 'button';
      item.innerHTML = `<span class="legend-dot" style="background:${p.color}"></span><span>${p.abbr}</span><span class="legend-seats">${seats}</span>`;
      item.addEventListener('click', () => navigate(`party/${key}`));
      container.appendChild(item);
    });
}

/* ============================================================
   Spectrum chart
   ============================================================ */
function renderSpectrum() {
  const chart = document.getElementById('spectrum-chart');
  chart.querySelectorAll('.party-dot').forEach(d => d.remove());
  Object.entries(state.data.parties).forEach(([key, party]) => {
    if (!party.spectrum) return;
    const dot = document.createElement('button');
    dot.className = 'party-dot';
    dot.type = 'button';
    // x maps directly; y is inverted (0 = progressive at bottom, 100 = traditional at top)
    dot.style.left = party.spectrum.x + '%';
    dot.style.top = (100 - party.spectrum.y) + '%';
    dot.setAttribute('aria-label', localized(party.name));
    dot.innerHTML = `
      <span class="party-dot-circle" style="background:${party.color}">${key.slice(0, 3)}</span>
      <span class="party-dot-label">${party.abbr}</span>`;
    dot.addEventListener('click', () => navigate(`party/${key}`));
    chart.appendChild(dot);
  });
}

/* ============================================================
   Initiatives (with filter + search)
   ============================================================ */
function renderInitiatives() {
  const grid = document.getElementById('initiatives-grid');
  if (!grid) return;
  grid.innerHTML = '';

  const q = state.search.trim().toLowerCase();
  const items = state.data.initiatives.filter(init => {
    if (state.filter !== 'all' && init.type !== state.filter) return false;
    if (!q) return true;
    const hay = (localized(init.title) + ' ' + localized(init.desc)).toLowerCase();
    return hay.includes(q);
  });

  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'init-empty';
    empty.textContent = t('init.none');
    grid.appendChild(empty);
    return;
  }

  items.forEach(init => {
    const card = document.createElement('button');
    card.className = 'initiative-card';
    card.type = 'button';
    const title = localized(init.title);
    const desc = localized(init.desc);
    const date = localized(init.date);
    const shortDesc = desc.length > 130 ? desc.slice(0, 130).trimEnd() + '…' : desc;

    card.innerHTML = `
      <span class="initiative-type type-${init.type}">${t('type.' + init.type)}</span>
      <span class="initiative-title" style="display:block">${title}</span>
      <span class="initiative-desc" style="display:block">${shortDesc}</span>
      <span class="initiative-meta">
        <span class="initiative-date">${date}</span>
        <span class="initiative-status status-${init.status}">${t('status.' + init.status)}</span>
      </span>
      <span class="initiative-link">${t('init.readMore')} →</span>`;
    card.addEventListener('click', () => navigate(`initiative/${init.id}`));
    grid.appendChild(card);
  });
}

/* ============================================================
   Initiative page
   ============================================================ */
function renderInitiativePage(id) {
  const init = state.data.initiatives.find(i => i.id === id);
  if (!init) { navigate(''); return; }

  const badge = document.getElementById('initiative-type-badge');
  badge.className = 'party-abbr';
  badge.style.background = init.type === 'initiative' ? 'var(--red)' : '#0064C8';
  badge.textContent = t('type.' + init.type);
  document.getElementById('initiative-title').textContent = localized(init.title);
  document.getElementById('initiative-date').textContent = localized(init.date);

  const fillFin = (fkey) => t(fkey).replace('{name}', localized(init.title));
  document.getElementById('initiative-content').innerHTML = `
    <p class="canton-intro">${localized(init.desc)}</p>
    <div class="detail-facts">
      <div class="detail-fact"><strong>${t('modal.status')}</strong><span>${t('status.' + init.status)}</span></div>
      <div class="detail-fact"><strong>${t('modal.date')}</strong><span>${localized(init.date)}</span></div>
      ${init.outcome ? `<div class="detail-fact"><strong>${t('modal.outcome')}</strong><span>${localized(init.outcome)}</span></div>` : ''}
      ${init.author ? `<div class="detail-fact"><strong>${t('modal.author')}</strong><span>${init.author}</span></div>` : ''}
    </div>
    <p class="detail-source">${t('modal.source')}</p>
    <div style="margin-top:20px">
      <a class="resource-link" href="${init.url}" target="_blank" rel="noopener">${t('modal.official')} <span class="arrow">↗</span></a>
    </div>
    <h3 class="canton-section-title" style="margin-top:48px">${t('init.financing.title')}</h3>
    ${renderInitiativeFinancing(id, fillFin)}`;
}

function renderInitiativeFinancing(id, fillFin) {
  const sides = state.data.financing.initiatives[id];
  if (!sides) {
    return `
      <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">💰</div><p>${fillFin('init.financing.desc')}</p></div>
      <div style="margin-top:16px">
        <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener">${t('init.financing.link')} <span class="arrow">↗</span></a>
      </div>`;
  }
  const sideBlock = (sideKey, labelKey) => `
    <div>
      <h4 class="canton-section-title" style="font-size:16px">${t(labelKey)}</h4>
      <div class="detail-facts" style="margin-bottom:12px">
        <div class="detail-fact"><strong>${t('financing.total')}</strong><span>${formatCHF(sides[sideKey].totalRevenue)}</span></div>
        <div class="detail-fact"><strong>${t('financing.actorsReporting')}</strong><span>${sides[sideKey].actorCount}</span></div>
      </div>
      ${renderDonorList(sides[sideKey].largeDonors)}
    </div>`;
  return `
    <div class="canton-grid" style="margin-top:8px">
      ${sideBlock('pro', 'financing.pro')}
      ${sideBlock('contra', 'financing.contra')}
    </div>
    ${renderFinancingSource()}
    <div style="margin-top:16px">
      <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener">${t('init.financing.link')} <span class="arrow">↗</span></a>
    </div>`;
}

/* ============================================================
   Map
   ============================================================ */
function buildMap() {
  const svg = document.getElementById('swiss-map');
  const tooltip = document.getElementById('map-tooltip');
  const NS = 'http://www.w3.org/2000/svg';

  Object.entries(MAP_PATHS).forEach(([code, geo]) => {
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', geo.d);
    path.setAttribute('id', code);
    path.setAttribute('tabindex', '0');
    path.setAttribute('role', 'button');
    const name = () => state.data.cantons[code]?.name || code;
    path.setAttribute('aria-label', name());

    const showTip = e => {
      tooltip.textContent = name();
      tooltip.style.opacity = '1';
      const x = (e.clientX ?? window.innerWidth / 2);
      const y = (e.clientY ?? window.innerHeight / 2);
      tooltip.style.left = (x - tooltip.offsetWidth / 2) + 'px';
      tooltip.style.top = (y - tooltip.offsetHeight - 14) + 'px';
    };
    path.addEventListener('mousemove', showTip);
    path.addEventListener('mouseleave', () => { tooltip.style.opacity = '0'; });
    path.addEventListener('focus', () => {
      const rect = path.getBoundingClientRect();
      tooltip.textContent = name();
      tooltip.style.opacity = '1';
      tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
      tooltip.style.top = (rect.top - tooltip.offsetHeight - 8) + 'px';
    });
    path.addEventListener('blur', () => { tooltip.style.opacity = '0'; });
    path.addEventListener('click', () => navigate(`canton/${code}`));
    path.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(`canton/${code}`); }
    });
    svg.appendChild(path);

    const label = document.createElementNS(NS, 'text');
    label.setAttribute('x', geo.c[0]);
    label.setAttribute('y', geo.c[1]);
    label.setAttribute('class', 'map-label');
    label.textContent = code;
    svg.appendChild(label);
  });
}

/* ============================================================
   Canton page
   ============================================================ */
function renderCantonPage(code) {
  const c = state.data.cantons[code];
  if (!c) { navigate(''); return; }

  document.getElementById('canton-title').textContent = c.name;
  document.getElementById('canton-capital').textContent = `${t('canton.capital')}: ${c.capital}`;
  document.getElementById('canton-emblem').textContent = code;

  document.getElementById('canton-stats').innerHTML = `
    <div class="canton-stat"><div class="canton-stat-val">${c.pop}</div><div class="canton-stat-label">${t('canton.stat.pop')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.area}</div><div class="canton-stat-label">${t('canton.stat.area')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.seats}</div><div class="canton-stat-label">${t('canton.stat.seats')}</div></div>
    <div class="canton-stat"><div class="canton-stat-val">${c.joined}</div><div class="canton-stat-label">${t('canton.stat.joined')}</div></div>`;

  const fill = (key) => t(key).replace('{name}', c.name);
  document.getElementById('canton-content').innerHTML = `
    <p class="canton-intro">${c.desc}</p>
    <div class="canton-grid">
      <div>
        <h3 class="canton-section-title">${t('canton.elections')}</h3>
        <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">🗳</div><p>${fill('canton.empty.elections')}</p></div>
      </div>
      <div>
        <h3 class="canton-section-title">${t('canton.municipalities')}</h3>
        <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">🏘</div><p>${fill('canton.empty.municipalities')}</p></div>
      </div>
      <div>
        <h3 class="canton-section-title">${t('canton.parliament')}</h3>
        <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">🏛</div><p>${fill('canton.empty.parliament')}</p></div>
      </div>
      <div>
        <h3 class="canton-section-title">${t('canton.initiatives')}</h3>
        <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">📜</div><p>${fill('canton.empty.initiatives')}</p></div>
      </div>
    </div>
    <p class="canton-sources">${t('canton.sources')}</p>`;
}

/* ============================================================
   Party page
   ============================================================ */
function renderPartyPage(key) {
  const p = state.data.parties[key];
  if (!p) { navigate(''); return; }

  const hero = document.getElementById('party-hero');
  hero.style.background = `linear-gradient(135deg, ${p.color}22 0%, var(--white) 100%)`;
  const badge = document.getElementById('party-abbr-badge');
  badge.style.background = p.color;
  badge.textContent = p.abbr;
  document.getElementById('party-name-large').textContent = localized(p.name);
  document.getElementById('party-desc-large').textContent = localized(p.desc);

  const posGrid = document.getElementById('party-positions');
  posGrid.innerHTML = '';
  (p.positions || []).forEach(pos => {
    const card = document.createElement('div');
    card.className = 'position-card';
    const barLabel = `${t('party.positionLevel')}: ${pos.level}%`;
    card.innerHTML = `
      <div class="position-topic">${t('topic.' + pos.topic)}</div>
      <div class="position-stance">${localized(pos.stance)}</div>
      <div class="position-bar" role="img" aria-label="${barLabel}"><div class="position-bar-fill" style="width:0%;background:${p.color}"></div></div>`;
    posGrid.appendChild(card);
    // animate bar after paint
    requestAnimationFrame(() => {
      card.querySelector('.position-bar-fill').style.width = pos.level + '%';
    });
  });

  const fillFin = (fkey) => t(fkey).replace('{name}', localized(p.name));
  document.getElementById('party-extra').innerHTML = `
    <div>
      <h3 class="canton-section-title">${t('party.rep')}</h3>
      <div style="display:flex;gap:24px;flex-wrap:wrap">
        <div class="stat-box"><div class="big" style="color:${p.color}">${p.ncSeats}</div><div class="lbl">${t('party.nc')}</div></div>
        <div class="stat-box"><div class="big" style="color:${p.color}">${p.csSeats}</div><div class="lbl">${t('party.cs')}</div></div>
      </div>
    </div>
    <div>
      <h3 class="canton-section-title">${t('party.resources')}</h3>
      <div style="display:flex;flex-direction:column;gap:12px">
        <a class="resource-link" href="${p.website}" target="_blank" rel="noopener">${t('party.website')} <span class="arrow">↗</span></a>
        <a class="resource-link" href="https://www.parlament.ch/en/organe/groups" target="_blank" rel="noopener">${t('party.group')} <span class="arrow">↗</span></a>
      </div>
      <p style="margin-top:20px;font-size:12px;color:var(--mid);line-height:1.6">${t('party.disclaimer')}</p>
    </div>
    <div style="grid-column:1/-1">
      <h3 class="canton-section-title">${t('party.financing.title')}</h3>
      ${renderPartyFinancing(key, p, fillFin)}
    </div>`;
}

function renderPartyFinancing(key, p, fillFin) {
  const f = state.data.financing.parties[key];
  if (!f) {
    return `
      <div class="empty-state"><div class="empty-state-icon" aria-hidden="true">💰</div><p>${fillFin('party.financing.desc')}</p></div>
      <div style="margin-top:16px">
        <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener">${t('party.financing.link')} <span class="arrow">↗</span></a>
      </div>`;
  }
  return `
    <div style="display:flex;gap:24px;flex-wrap:wrap;margin-bottom:20px">
      <div class="stat-box"><div class="big" style="color:${p.color}">${formatCHF(f.totalRevenue)}</div><div class="lbl">${t('financing.total')} (${f.year})</div></div>
    </div>
    <div class="detail-facts">
      <div class="detail-fact"><strong>${t('financing.monetary')}</strong><span>${formatCHF(f.monetaryDonations)}</span></div>
      <div class="detail-fact"><strong>${t('financing.nonMonetary')}</strong><span>${formatCHF(f.nonMonetaryDonations)}</span></div>
      <div class="detail-fact"><strong>${t('financing.events')}</strong><span>${formatCHF(f.events)}</span></div>
      <div class="detail-fact"><strong>${t('financing.sales')}</strong><span>${formatCHF(f.sales)}</span></div>
      <div class="detail-fact"><strong>${t('financing.membershipFees')}</strong><span>${formatCHF(f.membershipFees)}</span></div>
      <div class="detail-fact"><strong>${t('financing.mandateFees')}</strong><span>${formatCHF(f.mandateFees)}</span></div>
    </div>
    <h4 class="canton-section-title" style="font-size:16px;margin-top:24px">${t('financing.topDonors')}</h4>
    ${renderDonorList(f.largeDonors)}
    ${renderFinancingSource()}
    <div style="margin-top:16px">
      <a class="resource-link" href="https://politikfinanzierung.efk.admin.ch" target="_blank" rel="noopener">${t('party.financing.link')} <span class="arrow">↗</span></a>
    </div>`;
}

/* ============================================================
   Router (hash-based, shareable URLs)
   ============================================================ */
function parseHash() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [view, id] = raw.split('/');
  return { view: view || 'home', id: id || null };
}

function navigate(path) {
  location.hash = path ? `#/${path}` : '#/';
}

function showView(name) {
  document.getElementById('home-content').style.display = name === 'home' ? 'block' : 'none';
  document.getElementById('canton-page').classList.toggle('active', name === 'canton');
  document.getElementById('party-page').classList.toggle('active', name === 'party');
  document.getElementById('initiative-page').classList.toggle('active', name === 'initiative');
}

function handleRoute() {
  const { view, id } = parseHash();
  if (view === 'canton' && id) {
    renderCantonPage(id);
    showView('canton');
  } else if (view === 'party' && id) {
    renderPartyPage(id);
    showView('party');
  } else if (view === 'initiative' && id) {
    renderInitiativePage(id);
    showView('initiative');
  } else {
    showView('home');
  }
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function scrollToSection(id) {
  if (parseHash().view !== 'home') {
    navigate('');
    // wait for home to show
    setTimeout(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' }), 60);
  } else {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' });
  }
  closeMobileMenu();
}

/* ============================================================
   Scroll reveal
   ============================================================ */
function initScrollReveal() {
  if (!('IntersectionObserver' in window)) {
    document.querySelectorAll('.reveal').forEach(el => el.classList.add('visible'));
    return;
  }
  const obs = new IntersectionObserver((entries) => {
    entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('visible'); obs.unobserve(e.target); } });
  }, { threshold: 0.1, rootMargin: '0px 0px -50px 0px' });
  document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
}

/* ============================================================
   Mobile menu
   ============================================================ */
function closeMobileMenu() { document.getElementById('navbar').classList.remove('menu-open'); }

/* ============================================================
   Wire up events
   ============================================================ */
function bindEvents() {
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => setLang(btn.dataset.lang));
  });
  document.querySelectorAll('[data-scroll]').forEach(el => {
    el.addEventListener('click', () => scrollToSection(el.dataset.scroll));
  });
  document.querySelectorAll('[data-home]').forEach(el => {
    el.addEventListener('click', (e) => { e.preventDefault(); navigate(''); });
  });

  const toggle = document.getElementById('nav-toggle');
  toggle.addEventListener('click', () => document.getElementById('navbar').classList.toggle('menu-open'));

  // Initiatives filter + search
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.filter = btn.dataset.filter;
      document.querySelectorAll('.filter-btn').forEach(b => {
        b.classList.toggle('active', b === btn);
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      renderInitiatives();
    });
  });
  const search = document.getElementById('init-search');
  search.addEventListener('input', () => { state.search = search.value; renderInitiatives(); });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMobileMenu();
  });

  // Nav shrink on scroll
  window.addEventListener('scroll', () => {
    document.getElementById('navbar').classList.toggle('scrolled', window.scrollY > 20);
  });

  // Routing
  window.addEventListener('hashchange', handleRoute);
}

/* ============================================================
   Boot
   ============================================================ */
async function init() {
  try {
    await loadData();
  } catch (err) {
    document.getElementById('load-error').style.display = 'block';
    console.error('Failed to load data', err);
    return;
  }

  // Language: saved → browser → en
  let lang = 'en';
  try { lang = localStorage.getItem('politikch-lang') || navigator.language?.slice(0, 2) || 'en'; } catch (e) {}
  if (!SUPPORTED_LANGS.includes(lang)) lang = 'en';
  state.lang = lang;

  buildMap();
  applyStaticTranslations();
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
    b.setAttribute('aria-pressed', b.dataset.lang === lang ? 'true' : 'false');
  });

  const ncSeats = {};
  const csSeats = {};
  Object.entries(state.data.parties).forEach(([k, p]) => {
    if (p.ncSeats) ncSeats[k] = p.ncSeats;
    if (p.csSeats) csSeats[k] = p.csSeats;
  });

  renderHemicycle('nc-hemicycle', ncSeats, 200);
  renderLegend('nc-legend', ncSeats);
  renderHemicycle('cs-hemicycle', csSeats, 46);
  renderLegend('cs-legend', csSeats);
  renderSpectrum();
  renderInitiatives();
  initScrollReveal();
  bindEvents();
  handleRoute();
}

document.addEventListener('DOMContentLoaded', init);
