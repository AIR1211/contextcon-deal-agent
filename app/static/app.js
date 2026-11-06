/* Avuno dashboard. No build step: plain JS against the API in docs/spec.txt. */
const $ = s => document.querySelector(s), $$ = s => [...document.querySelectorAll(s)], view = $('#view'), layer = $('#layer');
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const icon = n => `<svg class="icon"><use href="#i-${n}"/></svg>`;
const money = n => n == null ? '—' : '₹' + Number(n).toLocaleString('en-IN');
const count = n => n == null ? '—' : n >= 1e6 ? (n / 1e6).toFixed(1).replace(/\.0$/, '') + 'M' : n >= 1e4 ? Math.round(n / 1e3) + 'K' : Number(n).toLocaleString('en-IN');
const pct = n => n == null ? 'Unknown' : (n * 100).toFixed(1) + '%';
const day = s => s ? new Date(s).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : '';
const clock = s => s ? new Date(s).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
const initial = s => esc((s || '?').replace(/^demo_/, '').charAt(0).toUpperCase());

function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; t.setAttribute('role', 'status'); document.body.append(t); fx.toast(t); setTimeout(() => t.remove(), 4200); }
async function api(path, body) {
  const r = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) { const d = data.detail; throw new Error(typeof d === 'string' ? d : d?.[0]?.msg || `Request failed (${r.status})`); }
  return data;
}

const params = new URLSearchParams(location.search);
const S = { role: params.get('role') || localStorage.role || 'creator', creator: params.has('creator') ? params.get('creator') || null : localStorage.creator || null, company: params.has('company') ? params.get('company') || null : localStorage.company || null, es: null };
const save = () => { localStorage.role = S.role; S.creator ? localStorage.creator = S.creator : localStorage.removeItem('creator'); S.company ? localStorage.company = S.company : localStorage.removeItem('company'); };

const VERIFY = { verified: ['b-ok', 'Verified'], weak_match: ['b-warn', 'Weak match'], partly_verified: ['b-info', 'Partly verified'], cannot_verify: ['b-none', "Can't verify"], blocked: ['b-err', 'Blocked'], contact_left: ['b-warn', 'Contact left'] };
const verifyBadge = s => { const [c, l] = VERIFY[s] || ['b-none', s]; return `<span class="badge ${c}"><i></i>${esc(l)}</span>`; };
function dealBadge(d) {
  if (d.state === 'done') return '<span class="badge b-done"><i></i>Completed</span>';
  if (d.state === 'blocked') return '<span class="badge b-err"><i></i>Blocked</span>';
  if (d.state === 'no_deal') return '<span class="badge b-none"><i></i>No deal</span>';
  if (d.paused?.kind === 'signature') return '<span class="badge b-info"><i></i>Ready to sign</span>';
  if (d.paused && !d.paused.question) return '<span class="badge b-info"><i></i>Waiting</span>';
  if (d.paused) return '<span class="badge b-warn"><i></i>Needs review</span>';
  return '<span class="badge b-info"><i></i>In progress</span>';
}
const meter = (label, v, cls = '') => `<div class="mline"><div><span>${label}</span><b class="num">${v ?? '—'}</b></div><div class="meter ${cls}" role="img" aria-label="${label} ${v} of 100"><i style="width:${Math.max(0, Math.min(100, v || 0))}%"></i></div></div>`;
const chip = (t = 'Fetching from Crustdata') => `<span class="live-chip"><i></i>${esc(t)}</span>`;
const working = (t, live) => `<div class="fetch">${live ? chip() : ''}<p>${esc(t)}</p><div class="stripe" role="progressbar" aria-label="${esc(t)}"></div></div>`;
const spinner = (t, live) => `<div class="card">${working(t, live)}</div>`;
let APP = { watchable_pace: true, pace_ms: 900, show_data_calls: true };
const fieldNames = { founded: 'Founded', lead: 'Person to approach', headcount: 'Headcount', last_funding: 'Last funding', company_data: 'Company data', followers: 'Followers', engagement_rate: 'Engagement', median_likes: 'Median likes', median_comments: 'Median comments', company: 'Company', group: 'Company group', domain: 'Domain check', name_match: 'Name match', current_employer: 'Current employer', employment: 'Employment', gstin_format: 'GSTIN format', instagram_followers: 'Instagram followers', influencer_roles: 'Influencer roles' };
function factValue(f) { if (f.field === 'engagement_rate') return pct(f.value); if (typeof f.value === 'number') return count(f.value); if (f.value === true) return 'Valid'; if (f.value === false) return 'Invalid'; return f.value; }
const factRows = fs => (fs || []).map(f => `<div class="fact"><div><b class="small">${esc(fieldNames[f.field] || f.field)}</b><small>${esc(f.source)}${f.as_of ? ' · ' + esc(day(f.as_of)) : ''}</small></div><div class="row" style="gap:6px;justify-content:flex-end"><span class="small">${esc(factValue(f))}</span>${f.is_mock ? '<span class="tag">Mock</span>' : ''}</div></div>`).join('') || '<p class="faint small">No facts could be checked.</p>';

/* Shell */
function nav() {
  const items = S.role === 'creator' ? [['home', 'Home', 'home'], ['brands', 'Brands', 'brands'], ['applications', 'Applications', 'send'], ['deals', 'Deals', 'deals'], ['messages', 'Messages', 'mail'], ['settings', 'Settings', 'gear']] : [['request', 'New request', 'send'], ['home', 'Home', 'home'], ['offers', 'Offers', 'inbox'], ['creators', 'Creators', 'creators'], ['deals', 'Deals', 'deals'], ['messages', 'Messages', 'mail'], ['settings', 'Settings', 'gear']];
  const now = (location.hash.slice(2) || 'home').split('/')[0];
  $('#nav').innerHTML = items.map(([h, l, i]) => `<a href="#/${h}" class="${now === h ? 'on' : ''}" ${now === h ? 'aria-current="page"' : ''}>${icon(i)}${l}</a>`).join('');
  $('#r-creator').className = S.role === 'creator' ? 'on' : ''; $('#r-brand').className = S.role === 'brand' ? 'on' : '';
}
$('#r-creator').onclick = () => setRole('creator'); $('#r-brand').onclick = () => setRole('brand');
function setRole(r) { S.role = r; save(); location.hash = '#/home'; route(); }
async function foot() { try { const s = await api('/api/status'); $('#foot').innerHTML = `<b>Live data</b> from Crustdata${s.credit_balance != null ? `<br>${Math.round(s.credit_balance).toLocaleString('en-IN')} credits left` : ''}<br>Payments, signatures and outbox are mocks. Brand accounts in demos are played by our team.`; } catch { $('#foot').textContent = 'Payments, signatures and outbox are mocks.'; } }

async function route() {
  if (S.es) { S.es.close(); S.es = null; }
  clearTimeout(S.caseTimer);
  save(); nav(); layer.innerHTML = '';
  const [page, id] = (location.hash.slice(2) || 'home').split('/');
  try {
    if (page === 'deals' && id) return await dealRoom(id);
    if (page === 'request' && id) return await caseRoom(id);
    const views = { request: requestPage, home: S.role === 'creator' ? creatorHome : brandHome, brands, creators, deals, messages, applications: applicationsPage, offers: offersPage, settings: settingsPage };
    await (views[page] || views.home)();
    fx.page(view);
  } catch (e) { view.innerHTML = `<div class="card empty"><h2>That didn't load</h2><p class="muted mt2">${esc(e.message)}</p></div>`; }
}
addEventListener('hashchange', route);

/* Creator home */
async function loadCreator() { if (!S.creator) return null; try { return await api(`/api/creators/${S.creator}`); } catch { S.creator = null; save(); return null; } }
async function creatorHome() {
  const c = await loadCreator();
  if (!c) return onboardCreator();
  const s = c.stats || {}, [ds, ledger] = await Promise.all([api('/api/deals'), api('/api/outbox')]);
  const mine = ds.filter(d => d.creator_ids.includes(c.id)), earned = ledger.filter(a => a.kind === 'mock_payout' && a.payload.creator === c.id).reduce((n, a) => n + a.payload.amount, 0);
  const noPosts = !s.reels_read && s.followers != null;
  view.innerHTML = `<div class="head"><div><h1>Welcome back, @${esc(c.handle)}</h1><p class="muted">Your limits are private. Avuno handles the rest and asks only when your answer changes the result.</p></div><a class="btn b1" href="#/brands">Find brands ${icon('arrow')}</a></div>
  <div class="grid g4">${[['In progress', mine.filter(d => !['done', 'blocked', 'no_deal'].includes(d.state)).length], ['Completed', mine.filter(d => d.state === 'done').length], ['Earned (mock)', money(earned)], ['Needs your answer', mine.filter(d => d.paused?.question).length]].map(([l, v]) => `<div class="card tile"><div class="l">${l}</div><div class="v num">${v}</div></div>`).join('')}</div>
  <div class="split mt"><div class="stack"><div class="card"><div class="row" style="align-items:flex-start;gap:var(--s4)"><div class="avatar">${initial(c.handle)}</div><div style="flex:1;min-width:220px"><div class="row between"><div><h2 style="font-size:26px">@${esc(c.handle)}</h2><p class="muted small">${esc(c.niche)}${c.is_mock ? ' · <span class="tag">Mock profile</span>' : ''}</p></div>${c.status === 'read' ? '<span class="badge b-ok"><i></i>Public stats read</span>' : '<span class="badge b-none"><i></i>Can\'t verify</span>'}</div>
  <div class="stats3 mt"><div><b class="num">${count(s.followers)}</b><span>Followers</span></div><div><b class="num">${pct(s.engagement_rate)}</b><span>Engagement</span></div><div><b class="num">${count(s.median_likes)}</b><span>Median likes</span></div></div></div></div>
  ${noPosts ? '<div class="ask mt"><div><h4>No public posts to read</h4><p class="small muted">Engagement is unknown, not low. Add analytics or post a reel to raise your confidence score.</p></div></div>' : ''}
  ${s.engagement_anomalous ? '<div class="ask mt"><div><h4>Your sampled posts look unusually viral</h4><p class="small muted">We don\'t use that engagement in your score. Share analytics for a fairer one.</p></div></div>' : ''}
  ${c.status !== 'read' ? `<div class="ask bad mt"><div><h4>We couldn't read this profile</h4><p class="small muted">It may be private or unavailable. Nothing has been assumed about you.</p></div></div>` : ''}</div>
  ${dealList(mine, 'Your deals')}</div>
  <div class="stack"><div class="card evidence-card"><h3>Evidence</h3><div class="mt2">${factRows(c.facts)}</div></div>
  <div class="card"><h3>Got an offer already?</h3><p class="small muted mt2">Paste it, however messy. We'll check who sent it and flag bad terms.</p><textarea id="offer" class="mt3" rows="4" placeholder="Hi! We'd love to work with you..."></textarea><button class="btn b1 sm mt3" id="rev">Review this offer</button><div id="revo"></div></div>
  <div class="card flat"><div class="row between"><h3>Prove it's you</h3>${c.ownership_verified ? '<span class="badge b-ok"><i></i>Verified</span>' : ''}</div><p class="small muted mt2">Put this code in your Instagram bio, then check. No login needed.</p><p class="mono mt2"><b>${esc(localStorage['code:' + c.id] || 'Shown when you register on this device')}</b></p><button class="btn b2 sm mt3" id="own">Check my bio</button><p class="small muted mt2" id="ownr"></p></div>
  <button class="btn b2" id="reset">Use another handle</button></div></div>`;
  $('#own').onclick = async () => { $('#ownr').textContent = 'Checking…'; const r = await api(`/api/creators/${c.id}/check-ownership`, {}); $('#ownr').textContent = r.reason; if (r.verified) route(); };
  $('#reset').onclick = () => { S.creator = null; route(); };
  $('#rev').onclick = async () => {
    if (!$('#offer').value.trim()) return;
    $('#revo').innerHTML = '<p class="small muted mt2"><span class="spin"></span> Checking the terms and the sender…</p>';
    const r = await api('/api/offers/review', { text: $('#offer').value, creator_id: c.id });
    const [cls, label] = { reject: ['b-err', 'Do not accept'], counter: ['b-warn', 'Ask for changes'], clarify: ['b-info', 'Needs more detail'], fair: ['b-ok', 'Looks fair'] }[r.verdict];
    $('#revo').innerHTML = `<div class="mt3"><span class="badge ${cls}"><i></i>${label}</span>${r.findings.map(f => `<div class="fact"><div><b class="small">${esc(f.problem)}</b><small>${esc(f.proposed_change)}</small></div></div>`).join('') || '<p class="small muted mt2">No problems found against our published rules.</p>'}${r.verification ? `<p class="cap faint mt2">Brand: ${esc((VERIFY[r.verification.brand_status] || [, r.verification.brand_status])[1])}. Sender: ${esc((VERIFY[r.verification.sender_status] || [, r.verification.sender_status])[1])}.</p>` : ''}<p class="cap faint mt2">${esc(r.note)}</p></div>`;
  };
}
function onboardCreator() {
  view.innerHTML = `<div class="onb"><div><p class="cap" style="letter-spacing:.14em;color:var(--ochre-deep)">FOR CREATORS, SMALL OR BIG</p><h1 class="hero-title mt2">Brand deals, handled from first pitch to paid invoice.</h1><p class="muted mt" style="font-size:16px;max-width:520px">Any size of following. Avuno reads your public stats, finds brands likely to buy, negotiates within your limits, and holds the money before you start work.</p></div>
  <form class="card" id="f"><h2 style="font-size:26px;margin-bottom:var(--s4)">Start with your handle</h2>
  <label class="f"><span>Instagram handle</span><input name="handle" required placeholder="@yourhandle" autocomplete="off"></label>
  <label class="f"><span>Your niche <small>(in your own words)</small></span><input name="niche" required placeholder="e.g. home cooking, thrift fashion, mehendi art"></label>
  <label class="f"><span>Lowest price per reel <small>(private, never shown to brands)</small></span><input name="floor" type="number" min="0" placeholder="Leave blank for our estimate"></label>
  <label class="f"><span>Audience in India, % <small>(optional, self-reported)</small></span><input name="aud" type="number" min="0" max="100"></label>
  <button class="btn b1" style="width:100%">Read my public stats ${icon('arrow')}</button><p class="cap faint mt3" id="st">Takes up to a minute. Public pages only, no login.</p><div id="samples" class="mt3"></div></form></div>`;
  api('/api/demo/sample-creators', {}).then(() => api('/api/creators')).then(all => {
    const mock = all.filter(x => x.is_mock && x.status === 'read');
    if (mock.length) { $('#samples').innerHTML = `<p class="cap faint">Or try a sample account (labelled mock)</p><div class="row mt2" style="gap:6px">${mock.map(m => `<button type="button" class="btn b3 sm" data-m="${esc(m.id)}">@${esc(m.handle.replace(/^demo_/, ''))}</button>`).join('')}</div>`; $$('[data-m]').forEach(b => b.onclick = () => { S.creator = b.dataset.m; S.role = 'creator'; location.hash = '#/brands'; route(); }); }
  }).catch(() => {});
  $('#f').onsubmit = async e => {
    e.preventDefault(); const f = new FormData(e.target), b = e.target.querySelector('button'); b.disabled = true; $('#st').innerHTML = '<span class="spin"></span> Reading your profile and recent reels…';
    try { const c = await api('/api/creators', { handle: f.get('handle'), niche: f.get('niche'), limits: { floor_reel: f.get('floor') ? +f.get('floor') : null }, audience_country_pct: f.get('aud') ? +f.get('aud') : null }); localStorage['code:' + c.id] = c.ownership_code; await watchRead(c.id, $('#st')); S.creator = c.id; S.role = 'creator'; route(); }
    catch (x) { b.disabled = false; $('#st').textContent = x.message; }
  };
}

/* Brands for a creator */
async function brands(quiet) {
  const c = await loadCreator();
  if (!c) { location.hash = '#/home'; return; }
  if (quiet !== true) view.innerHTML = spinner(`Searching for "${c.niche}" brands and scoring them against live company data`, true);
  const [m, cst] = await Promise.all([api(`/api/creators/${c.id}/matches`), api(`/api/settings/creator/${c.id}`)]), sel = new Set();
  view.innerHTML = `<div class="head"><div><h1>Brands likely to buy</h1><p class="muted">${m.matches.length} above the threshold of ${m.threshold}, for ${esc(c.niche)}. ${m.open_niche ? `"${esc(c.niche)}" names no product category, so these are brands hiring for creator marketing across niches. ` : ''}${esc(m.note)}</p></div><div class="autobar"><div><b class="small">Auto Deal</b><div class="cap faint">Sends your ${esc(cst.auto_pack)} pack to brands above ${cst.auto_min_likelihood} likelihood</div></div><label class="switch"><input type="checkbox" id="auto" ${cst.auto_deal ? 'checked' : ''} aria-label="Auto Deal"><span></span></label></div></div>
  ${m.assessing ? `<div class="card" style="margin-bottom:var(--s4)">${working(`Scoring ${m.assessing} more brands. They appear here as each one is checked.`, true)}</div>` : ''}
  <form class="searchrow" id="bs"><input id="bq" placeholder="Apply to a specific brand: name or domain, e.g. nykaa.com" aria-label="Find a brand"><button class="btn b2">Find brand</button></form><div id="bsr"></div>
  <div class="grid g2">${m.matches.map(b => `<article class="card"><div class="row between" style="align-items:flex-start"><div class="row"><div class="avatar sm ink">${initial(b.name)}</div><div><h3>${esc(b.name)}</h3><p class="cap faint">${esc(b.domain || 'No website')}${b.size_range ? ' · ' + esc(b.size_range) + ' staff' : ''}</p></div></div>${verifyBadge(b.status)}</div>
  <div class="row mt" style="gap:var(--s4)">${meter('Likelihood', b.likelihood)}${meter('Confidence', b.confidence, 'c')}</div><p class="whyline">${esc(b.why || '')}</p><details class="ev"><summary>Evidence</summary><ul class="why">${b.reasons.map(r => `<li>${esc(r)}</li>`).join('')}</ul></details>${b.decided_by ? `<p class="tie">Ranked above the next brand: ${esc(b.decided_by)}</p>` : ''}
  <div class="row between mt"><label class="row small" style="gap:6px;cursor:pointer"><input type="checkbox" data-c="${esc(b.company_id)}" style="width:auto"> Compare</label><button class="btn b1 sm" data-p="${esc(b.company_id)}" data-n="${esc(b.name)}">Media packs ${icon('arrow')}</button></div></article>`).join('')}</div>
  ${m.matches.length ? '' : m.assessing ? '<div class="card empty"><span class="spin"></span><h2 class="mt3">Scoring brands now</h2><p class="muted mt2">They appear here as soon as each one is checked.</p></div>' : '<div class="card empty"><h2>No brands above the threshold yet</h2><p class="muted mt2">The brands below show why.</p></div>'}
  <div id="sel"></div><details class="card flat mt"><summary>${m.rejected.length} ${m.rejected.length === 1 ? 'brand' : 'brands'} not suggested, and why</summary>${m.rejected.map(b => `<div class="fact"><b class="small">${esc(b.name)}</b><span class="small muted" style="text-align:right">Likelihood ${b.likelihood}. ${esc(b.reasons.join(' '))}</span></div>`).join('') || '<p class="faint small mt2">None.</p>'}${m.not_assessed ? `<p class="faint small mt2">${m.not_assessed} more matching brands not assessed yet.</p>` : ''}</details>`;
  $$('[data-p]').forEach(b => b.onclick = () => packs(c, b.dataset.p, b.dataset.n));
  $('#auto').onchange = async e => { await api(`/api/settings/creator/${c.id}`, { auto_deal: e.target.checked }); toast(e.target.checked ? 'Auto Deal is on. Standard packs are going out to eligible brands.' : 'Auto Deal is off.'); };
  $('#bs').onsubmit = async e => { e.preventDefault(); if (!$('#bq').value.trim()) return; $('#bsr').innerHTML = `<div class="card" style="margin-bottom:var(--s4)">${working('Looking up this company', true)}</div>`; const r = await api(`/api/brands/search?q=${encodeURIComponent($('#bq').value)}`); $('#bsr').innerHTML = (r.length ? r.map(x => `<div class="card" style="margin-bottom:var(--s2)"><div class="row between"><div><h3>${esc(x.name)}</h3><p class="cap faint">${esc(x.domain || '')}</p></div><button class="btn b1 sm" data-f="${esc(x.company_id)}" data-n="${esc(x.name)}">Media packs ${icon('arrow')}</button></div></div>`).join('') : '<p class="small muted" style="margin-bottom:var(--s4)">No matching company found. Try its website domain.</p>'); $$('[data-f]').forEach(b => b.onclick = () => packs(c, b.dataset.f, b.dataset.n)); };
  if (m.assessing) setTimeout(() => { if (location.hash === '#/brands' && !layer.innerHTML && !sel.size && !$('#bq')?.value) brands(true).catch(() => {}); }, 5000);
  $$('[data-c]').forEach(x => x.onchange = () => { x.checked ? sel.add(x.dataset.c) : sel.delete(x.dataset.c); $('#sel').innerHTML = sel.size >= 2 ? `<div class="selbar"><span>${sel.size} brands selected</span><button class="btn b3 sm" id="cmp">Compare offers</button></div>` : ''; if (sel.size >= 2) $('#cmp').onclick = () => compare(c, [...sel]); });
}
async function compare(c, ids) {
  const r = await api(`/api/creators/${c.id}/compare-offers`, { company_ids: ids });
  drawer(`<div class="row between"><h2>Offers, ranked</h2>${closeBtn()}</div><p class="muted small mt2">Published order: pay, safer payment, fewer restrictions, fit, earliest offer, then a fair lot. These are estimates from simulated company limits.</p>
  <div class="stack mt">${r.offers.map(o => `<div class="card"><div class="row between"><h3>${o.rank}. ${esc(o.name)}</h3><b class="num" style="font-size:18px">${money(o.net)}</b></div><p class="small muted">You net · ${o.upfront_pct}% held upfront · ${o.usage_days} days usage · tier ${esc(o.tier)}</p>${o.decided_by ? `<p class="tie">Beats next: ${esc(o.decided_by)}</p>` : ''}</div>`).join('')}${r.no_offer.map(o => `<div class="card flat"><h3>${esc(o.name || o.company_id)}</h3><p class="small muted">${esc(o.reason)}</p></div>`).join('')}</div>`);
}
const closeBtn = () => `<button class="btn b2 sm" data-close aria-label="Close">${icon('x')}</button>`;
function drawer(html) { layer.innerHTML = `<div class="drawer-bg" data-close></div><aside class="drawer" role="dialog" aria-modal="true">${html}</aside>`; $$('[data-close]').forEach(x => x.onclick = () => { layer.innerHTML = ''; }); fx.drawer($('.drawer')); }

async function packs(c, companyId, name) {
  drawer(`<div class="row between"><h2>${esc(name)}</h2>${closeBtn()}</div>${spinner('Building packs…')}`);
  const p = await api(`/api/creators/${c.id}/packs/${companyId}`);
  let base = p.packs[1] || p.packs[0], cur = { ...base.terms };
  const num = (k, l, min, max) => `<label class="f"><span>${l}</span><input type="number" data-t="${k}" min="${min}" max="${max}" value="${cur[k]}"></label>`;
  const sel = (k, l, opts) => `<label class="f"><span>${l}</span><select data-t="${k}">${opts.map(o => `<option value="${o}" ${+cur[k] === o ? 'selected' : ''}>${o} days</option>`).join('')}</select></label>`;
  const paint = () => {
    $('#pk').innerHTML = p.packs.map((x, i) => `<button class="pack ${x === base ? 'on' : ''}" data-i="${i}"><div class="row between"><h4>${esc(x.name)}</h4><b class="num">${money(x.evaluation.list_price)}</b></div><p class="cap faint mt2">${x.terms.reels} reel, ${x.terms.stories} stories, ${x.terms.usage_days}d usage${x.terms.exclusivity_days ? `, ${x.terms.exclusivity_days}d exclusive` : ''}</p><p class="small muted mt2">You net about ${money(x.evaluation.creator_net_estimate)} · ${x.evaluation.close_estimate}% close estimate</p></button>`).join('');
    $('#tw').innerHTML = `<div class="grid g2">${num('reels', 'Reels', 0, 20)}${num('stories', 'Stories', 0, 50)}${sel('usage_days', 'Brand can reuse for', [...new Set([30, 60, 90, 180, cur.usage_days])].sort((a, b) => a - b))}${sel('exclusivity_days', 'Exclusivity', [...new Set([0, 30, 60, 90, cur.exclusivity_days])].sort((a, b) => a - b))}</div><label class="row small" style="gap:8px;cursor:pointer"><input type="checkbox" data-t="paid_ads" style="width:auto" ${cur.paid_ads ? 'checked' : ''}> Allow paid ads with my content</label>`;
    $$('[data-i]').forEach(b => b.onclick = () => { base = p.packs[+b.dataset.i]; cur = { ...base.terms }; paint(); $('#dl').innerHTML = ''; });
    $$('[data-t]').forEach(x => x.onchange = () => { cur[x.dataset.t] = x.type === 'checkbox' ? x.checked : +x.value; check(); });
  };
  const check = async () => {
    const r = await api(`/api/creators/${c.id}/packs/${companyId}/tweak`, { before: base.terms, after: cur });
    const cls = { improved: 'b-ok', worse: 'b-err', unchanged: 'b-none', blocked: 'b-err' }[r.verdict], sign = n => (n > 0 ? '+' : '') + n, label = { improved: 'Improved', worse: 'Worse', unchanged: 'No change', blocked: 'Outside your limits' }[r.verdict];
    $('#dl').innerHTML = `<div class="card mt"><div class="row between"><h3>Did this tweak help?</h3><span class="badge ${cls}"><i></i>${label}</span></div>${r.problem ? `<p class="small mt2">${esc(r.problem)}</p>` : ''}
    <div class="grid g3 mt3"><div><div class="cap faint">List price</div><b class="num">${sign(r.delta.list_price)}</b></div><div><div class="cap faint">Close estimate</div><b class="num">${sign(r.delta.close_estimate)} pts</b></div><div><div class="cap faint">Expected earnings</div><b class="num">${sign(r.delta.expected_earnings)}</b></div></div><p class="cap faint mt3">${esc(r.note)}</p></div>`;
    $('#go').disabled = r.verdict === 'blocked';
  };
  $('.drawer').innerHTML = `<div class="row between"><div><h2>Media packs for ${esc(name)}</h2><p class="small muted">Likelihood ${p.likelihood} · fit ${p.fit} · <span class="tag">Estimates</span></p></div>${closeBtn()}</div><div class="mt">${p.brief ? creatorDoc(p.brief.creator_brief, { note: `What ${name} is asking for. Read this before you apply. Budget and internal details are removed.` }) : `<div class="ask"><div><h3>No campaign brief yet</h3><p class="small">You can still apply, but a deal can't start until ${esc(name)} adds one.</p></div></div>`}</div><div class="stack mt" id="pk" style="gap:var(--s2)"></div><div class="card mt"><h3 style="margin-bottom:var(--s3)">Tweak it</h3><div id="tw"></div></div><div id="dl"></div>
  <button class="btn b1 mt" id="go" style="width:100%">Apply to this brand ${icon('send')}</button><button class="btn b2 mt2" id="sim" style="width:100%">Run a simulated deal instead</button><p class="cap faint mt2">Applying waits for the brand to choose. A simulated deal uses a stand-in for the brand. Nothing reaches anyone real either way.</p>`;
  $$('[data-close]').forEach(x => x.onclick = () => { layer.innerHTML = ''; });
  paint();
  fx.list($('.drawer'));
  $('#go').onclick = async () => { try { await api('/api/applications', { creator_id: c.id, company_id: companyId, terms: cur, pack: base.name }); toast(`Applied to ${name}.`); location.hash = '#/applications'; } catch (e) { toast(e.message); } };
  $('#sim').onclick = () => startDeal([c.id], companyId, cur);
}
async function startDeal(creatorIds, companyId, terms, extra = '') {
  const d = await api(`/api/deals${extra}`, { creator_ids: creatorIds, company_id: companyId, terms, pace_ms: APP.watchable_pace ? APP.pace_ms : 0 });
  location.hash = `#/deals/${d.id}`; return d;
}

/* Brand side */
async function loadCompany() { if (!S.company) return null; try { return await api(`/api/companies/${S.company}`); } catch { S.company = null; save(); return null; } }
async function requestPage() {
  const all = await api('/api/requests');
  view.innerHTML = `<div class="req-hero"><p class="cap" style="letter-spacing:.14em;color:var(--ochre-deep)">TELL US WHAT YOU NEED</p><h1 class="hero-title mt2">Paste the request. We'll do the job.</h1><p class="muted mt2" style="font-size:16px">An email, a WhatsApp message or a full brief, however messy. Avuno checks who's asking, finds creators, negotiates, signs and gets everyone paid. It only asks you when your answer changes the result.</p>
  <textarea id="rq" aria-label="The request" placeholder="Hi, we're launching…"></textarea><div class="row mt3" style="gap:var(--s2)"><button class="btn b1" id="rqgo">Run this request ${icon('arrow')}</button><label class="btn b2 sm" style="cursor:pointer">Upload a brief (PDF, .txt, .md)<input type="file" id="rqf" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" hidden></label><a class="small" href="#" id="rqform">Use the form instead</a><span class="small muted" id="rqs"></span></div>
  ${all.length ? `<div class="card mt"><h3>Earlier requests</h3><div class="mt2">${all.map(r => `<a class="req-row" href="#/request/${esc(r.id)}"><div class="grow"><b class="small">${esc(r.company_name || r.text.slice(0, 60))}</b></div><span class="small muted">${esc(caseStatus(r)[1])}</span></a>`).join('')}</div></div>` : ''}</div>`;
  $('#rqform').onclick = e => { e.preventDefault(); onboardBrand(); };
  $('#rqgo').onclick = async () => { const text = $('#rq').value; if (text.trim().length < 20) { $('#rqs').textContent = 'Please paste the whole request.'; return; } $('#rqgo').disabled = true; try { const c = await api('/api/requests', { text }); location.hash = `#/request/${c.id}`; } catch (x) { $('#rqgo').disabled = false; $('#rqs').textContent = x.message; } };
  $('#rqf').onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    $('#rqs').textContent = 'Reading ' + file.name + '…';
    try {
      if (/\.pdf$/i.test(file.name)) { const b64 = btoa(new Uint8Array(await file.arrayBuffer()).reduce((a, c) => a + String.fromCharCode(c), '')); $('#rq').value = (await api('/api/briefs/extract', { filename: file.name, b64 })).text; }
      else $('#rq').value = await file.text();
      $('#rqs').textContent = '';
    } catch (x) { $('#rqs').textContent = x.message; }
  };
}
function caseStatus(c) {
  if (c.finished) return ['b-ok', 'Finished'];
  if (c.stage === 'stopped') return ['b-err', 'Stopped'];
  if (c.stage === 'duplicate') return ['b-info', 'Same request'];
  if (c.paused) return ['b-warn', 'Needs an answer'];
  return ['b-info', 'Working'];
}
const CASE_STEPS = ['Read', 'Company', 'Sender', 'Creators', 'Deals', 'Paid'];
function caseAt(c) {
  if (c.finished) return 6;
  return { read: 0, company: 1, creators: 3, deals: 4 }[c.stage] ?? (c.read ? 1 : 0);
}
const STEP_WORDS = { read: 'Reading the request line by line', company: 'Checking the company and the sender on Crustdata', creators: 'Ranking creators on evidence, within the private budget', deals: 'Running each deal: pitch, negotiation, contract, re-check, signatures, funds, delivery, payout, invoice' };
function paintCase(c) {
  const [cls, label] = caseStatus(c), at = caseAt(c), stopped = STOP_STAGE(c), co = c.company, r = c.read;
  const tierLine = c.tier_terms ? `<p class="small mt2"><b>Payment terms set by this evidence:</b> ${c.tier_terms.upfront_pct}% held upfront${c.tier_terms.deal_cap ? `, up to ${money(c.tier_terms.deal_cap)} per deal` : ''}.</p>` : '';
  const creators = c.creators ? `<div class="card"><div class="row between"><h3>Creators, ranked on evidence</h3><span class="tag">Labelled mock accounts</span></div><p class="small muted mt2">${esc(String(c.ranked_total))} matched. Follower count isn't scored. Each creator's lowest price stays private.</p><div class="mt3">${c.creators.map((x, i) => `<div class="req-row ${x.outcome === 'chosen' ? 'chosen' : ''}"><span class="req-rank">${i + 1}</span><div class="grow"><b class="small">@${esc(x.handle)}</b> <span class="small muted">${x.followers != null ? count(x.followers) + ' followers · ' : ''}${esc(x.niche)} · fit ${x.fit}</span><p class="small muted" style="margin:2px 0 0">${esc(x.why)}</p></div><span class="badge ${x.outcome === 'chosen' ? 'b-ok' : 'b-none'}"><i></i>${{ chosen: 'Chosen', no_overlap: 'No price fits both', not_needed: 'Not needed' }[x.outcome]}</span></div>`).join('')}</div></div>` : '';
  const deals = c.deals?.length ? `<div class="card" id="casedeals"><h3>Deals</h3><div class="mt2">${c.deals.map(d => `<a class="req-row" href="#/deals/${esc(d.id)}"><div class="grow"><b class="small">@${esc(d.handle)}</b><span class="small muted"> · ${esc(STAGE[d.state] || d.state)}${d.price ? ' · ' + money(d.price) : ''}${d.invoice ? ' · invoice ' + esc(d.invoice.number) : ''}</span></div>${dealBadge(d)}</a>`).join('')}</div></div>` : '';
  view.innerHTML = `<div class="head"><div><p class="cap faint"><a href="#/request">Requests</a> / ${esc(c.id)}</p><h1 style="margin-top:4px">${esc(c.company_name || r?.name || 'New request')}</h1></div><span class="badge ${cls}"><i></i>${esc(label)}</span></div>
  ${!stopped && !c.paused && !c.finished ? `<div class="card">${working(STEP_WORDS[c.stage] || 'Working', c.stage === 'company')}${c.calls?.length ? `<p class="cap faint mt2">Latest lookup: ${esc(c.calls[c.calls.length - 1].source)}, ${c.calls[c.calls.length - 1].how === 'live' ? `live in ${c.calls[c.calls.length - 1].seconds.toFixed ? c.calls[c.calls.length - 1].seconds.toFixed(1) : c.calls[c.calls.length - 1].seconds}s` : 'from cache'}</p>` : ''}</div>` : ''}
  <div class="card mt"><div class="pipe">${CASE_STEPS.map((x, i) => `<div class="${stopped && i === at ? 'x' : i < at ? 'd' : i === at && !c.finished ? 'n' : ''}"><i></i>${x}</div>`).join('')}</div></div>
  ${c.paused ? `<div class="ask mt"><div style="flex:1"><h3>Your answer changes the result</h3><p class="small">${esc(c.paused.question)}</p>${c.paused.retry ? '' : `<div class="answer">${(c.paused.needs || []).map(k => `<input data-need="${esc(k)}" ${k === 'budget' ? 'type="number" min="0" placeholder="Budget in ₹"' : `placeholder="${k === 'company' ? 'Company name or website' : 'For example: skincare'}"`}>`).join('')}</div>`}</div><button class="btn b1" id="caseans">${c.paused.retry ? 'Try again' : 'Continue'}</button></div>` : ''}
  ${c.stage === 'stopped' ? `<div class="ask bad mt"><div><h3>Stopped, and nothing was started</h3><p class="small">${esc(c.reason)}</p></div></div>` : ''}
  ${c.stage === 'duplicate' ? `<div class="ask mt" id="casedup"><div><h3>One company, one record</h3><p class="small">${esc(c.reason)}</p></div><a class="btn b2 sm" href="#/request/${esc(c.duplicate_of)}">Open the first request</a></div>` : ''}
  ${c.finished ? `<div class="ask mt" id="casedone" style="background:var(--ok-bg);border-color:#C6DACB"><div><h3>Finished: ${c.deals.filter(d => d.state === 'done').length} of ${c.deals.length} deals signed, delivered and paid</h3><p class="small">${money(c.deals.reduce((n, d) => n + (d.brand_pays || 0), 0))} settled from a ${money(r.budget)} budget. ${c.shortfall ? esc(c.shortfall) + ' ' : ''}Contracts and invoices are below. Payments and signatures are mocks.</p></div></div>` : ''}
  <div class="split mt"><div class="stack">
    ${briefCard(r ? { text: c.text, fields: r.fields, flags: r.flags, missing: r.missing, sha: r.sha } : { text: c.text, fields: [], flags: [], missing: [] }, { title: 'The request, as it came in', note: 'Each detail on the right comes from a highlighted line. Anything not stated stays unknown.' })}
    ${co ? `<div class="card" id="caseco"><h3>Who is asking?</h3><div class="verdict mt2"><b>${esc(co.name)}${co.domain ? ` <span class="small muted">${esc(co.domain)}</span>` : ''}</b>${verifyBadge(co.status)}</div>${r.sender_name ? `<div class="verdict"><b>${esc(r.sender_name)}${r.sender_email ? ` <span class="small muted">${esc(r.sender_email)}</span>` : ''}</b>${verifyBadge(co.sender_status)}</div>` : ''}<ul class="why">${(co.reasons || []).map(x => `<li>${esc(x)}</li>`).join('')}</ul>${tierLine}<div class="mt3">${factRows([...(co.facts || []), ...(c.facts || [])])}</div></div>` : ''}
    ${creators}${deals}
  </div><div class="stack"><div class="card"><h3 style="margin-bottom:var(--s3)">Activity</h3><ul class="time">${(c.log || []).map(l => `<li>${esc(l.text)}<small>${esc(clock(l.at))}</small></li>`).join('')}</ul></div>
  ${(c.replies || []).length ? `<div class="card"><div class="row between"><h3>Replies sent</h3><span class="tag">Mock outbox</span></div><div class="mt2">${c.replies.map(m => `<details class="mail out"><summary><span class="mail-sub">${esc(m.subject)}</span></summary><p class="cap faint mt2">To ${esc(m.to)}</p><p class="small mt2">${esc(m.body)}</p></details>`).join('')}</div></div>` : ''}</div></div>`;
}
const STOP_STAGE = c => c.stage === 'stopped' || c.stage === 'duplicate';
async function caseRoom(id) {
  view.innerHTML = spinner('Opening the request…');
  let last = '', seen = {};
  const tick = async () => {
    const c = await api(`/api/requests/${id}`), sig = JSON.stringify(c);
    if (sig !== last) {
      last = sig;
      paintCase(c);
      const lines = [...view.querySelectorAll('.time li')], rows = [...view.querySelectorAll('.bf-row, .req-row')], done = [...view.querySelectorAll('.pipe .d i')];
      if (!seen.first) fx.page(view);
      else { fx.fresh(lines.slice(seen.lines)); fx.fresh(rows.slice(seen.rows)); fx.grow(done.slice(seen.done)); if (seen.stage !== c.stage || seen.finished !== c.finished) fx.arrive(view.querySelector('.ask')); }
      Object.assign(seen, { first: true, lines: lines.length, rows: rows.length, done: done.length, stage: c.stage, finished: c.finished });
      if (c.company_id) { S.company = c.company_id; save(); }
      const go = $('#caseans');
      if (go) go.onclick = async () => { const values = Object.fromEntries($$('[data-need]').map(i => [i.dataset.need, i.dataset.need === 'budget' ? +i.value : i.value])); if (values.company && /\.[a-z]{2,}/i.test(values.company)) { values.domain = values.company; delete values.company; } await api(`/api/requests/${id}/answer`, values); };
    }
    if (location.hash.includes(id) && !c.finished && !STOP_STAGE(c)) S.caseTimer = setTimeout(() => tick().catch(() => {}), 500);
  };
  await tick();
}
async function brandHome() {
  const co = await loadCompany();
  if (!co) return requestPage();
  const [all, off, full] = await Promise.all([api('/api/deals'), api(`/api/companies/${co.id}/applications`), api(`/api/companies/${co.id}/brief`)]), mine = all.filter(d => d.company_id === co.id);
  view.innerHTML = `<div class="head"><div><h1>${esc(co.name)}</h1><p class="muted">${co.status === 'blocked' ? 'This company cannot use Avuno.' : 'Verification sets your payment terms. Size never counts against you: evidence does the work.'}${co.also_known_as?.length ? ` Also known as ${esc(co.also_known_as.join(', '))}.` : ''}</p></div>${co.status === 'blocked' ? '' : `<a class="btn b1" href="#/creators">Find creators ${icon('arrow')}</a>`}</div>
  ${co.status === 'blocked' ? `<div class="ask bad"><div><h3>Blocked</h3><p class="small">${esc((co.reasons || []).join(' '))}</p></div></div><div class="mt"></div>` : ''}
  ${off.open.length ? `<div class="ask" style="margin-bottom:var(--s4)"><div><h3>${off.open.length} ${off.open.length === 1 ? 'creator has' : 'creators have'} applied</h3><p class="small">Each comes with a media pack, evidence and a reason.</p></div><a class="btn b1" href="#/offers">Review offers ${icon('arrow')}</a></div>` : ''}
  <div class="grid g4" style="margin-bottom:var(--s4)">${[['Offers received', off.open.length + off.closed.length], ['Chosen', full?.budget?.creators_target ? `${mine.length} of ${full.budget.creators_target}` : mine.length], ['Paid', mine.filter(d => d.state === 'done').length], full?.budget?.pool ? ['Creator pool left', money(full.progress.remaining)] : ['Spent (mock)', money(mine.filter(d => d.state === 'done').reduce((n, d) => n + (d.settlement?.brand_pays || 0), 0))]].map(([l, v]) => `<div class="card tile"><div class="l">${l}</div><div class="v num">${v}</div></div>`).join('')}</div>
  <div class="split"><div class="stack"><div class="card"><div class="row between"><h3>Verification</h3><div class="row" style="gap:6px">${verifyBadge(co.status)}<span class="badge b-none">Tier ${esc(co.tier)}</span></div></div><ul class="why">${(co.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul></div>
  ${full?.sha ? briefCard(full) : '<div class="ask"><div><h3>Add your campaign brief</h3><p class="small">You need one before you can choose a creator.</p></div></div>'}
  ${questionsCard(full)}
  ${full?.creator_brief ? `<details class="card"><summary>What creators read</summary><div class="mt3">${creatorDoc(full.creator_brief)}</div></details>` : ''}
  <details class="card flat"><summary>${full?.sha ? 'Change the brief' : 'Add the brief'}</summary><textarea id="nb" rows="7" class="mt3">${esc(full?.text || '')}</textarea><button class="btn b1 sm mt3" id="nbs">Save brief</button></details>
  ${dealList(mine, 'Your deals')}</div>
  <div class="stack"><div class="card evidence-card"><h3>Evidence</h3><div class="mt2">${factRows(co.facts)}</div></div><button class="btn b2" id="reset">Register another company</button></div></div>`;
  $('#reset').onclick = () => { S.company = null; route(); };
  $('#nbs').onclick = async () => { try { await api(`/api/companies/${co.id}/brief`, { text: $('#nb').value }); toast('Brief saved.'); route(); } catch (e) { toast(e.message); } };
}
function onboardBrand() {
  view.innerHTML = `<div class="onb" style="align-items:start"><div><p class="cap" style="letter-spacing:.14em;color:var(--ochre-deep)">FOR BRANDS, SMALL OR BIG</p><h1 class="hero-title mt2">Creator campaigns without an agency.</h1><p class="muted mt" style="font-size:16px;max-width:520px">Find creators on evidence, not follower count. Clear contracts, and your money is only released when you approve the work. Any size of brand, with or without a website.</p>
  <div class="card flat mt5"><h3>Paste a request instead</h3><p class="small muted mt2">However messy. We fill the form, and flag what's missing rather than guessing.</p><textarea id="brief" class="mt3" rows="3" placeholder="need 2 reels for our snack launch, budget 30k, 60 day usage. Thanks, Neha Jain neha@snackly.in"></textarea><button class="btn b3 sm mt3" id="rb" type="button">Read this request</button><p class="small muted mt2" id="rbo"></p></div></div>
  <form class="card" id="f"><h2 style="font-size:26px;margin-bottom:var(--s4)">Verify your company</h2><label class="f"><span>Company name</span><input name="name" required></label><label class="f"><span>What you sell <small>(in your own words)</small></span><input name="niche" required placeholder="e.g. millet snacks, herbal skincare"></label><label class="f"><span>Website or domain <small>(optional)</small></span><input name="domain" placeholder="yourbrand.in"></label>
  <div class="grid g2"><label class="f"><span>Your name</span><input name="sender_name"></label><label class="f"><span>Work email</span><input name="sender_email" type="email"></label></div><div class="grid g2"><label class="f"><span>Instagram <small>(if no website)</small></span><input name="instagram" placeholder="@yourbrand"></label><label class="f"><span>GSTIN <small>(lookup is mocked)</small></span><input name="gstin"></label></div><label class="f"><span>Budget, ₹ <small>(private, never shown to creators)</small></span><input name="budget" type="number" min="0" required></label>
  <label class="f"><span>Campaign brief <small>(required. Creators read this before applying)</small></span><textarea name="campaign_brief" rows="7" required minlength="30" placeholder="Objective, deliverables, key message, dos and don'ts, timeline"></textarea></label>
  <div class="row" style="margin-bottom:var(--s3);gap:var(--s2)"><label class="btn b2 sm" style="cursor:pointer">Upload PDF, .txt or .md<input type="file" id="bf" accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown" hidden></label><button type="button" class="btn b3 sm" id="bs2">Use the sample brief</button><a class="small" href="/api/demo/sample-brief.pdf" target="_blank" rel="noopener">See an example</a></div><div id="bfo"></div>
  <button class="btn b1" style="width:100%">Verify ${icon('shield')}</button><p class="cap faint mt3" id="st"></p></form></div>`;
  const showRead = r => {
    const f = $('#f').elements;
    f.campaign_brief.value = r.text ?? f.campaign_brief.value;
    if (r.client && !f.name.value) f.name.value = r.client;
    if (r.product && !f.niche.value) f.niche.value = r.product.replace(/\(.*?\)/g, '').split('—').pop().trim();
    if (r.cap && !f.budget.value) f.budget.value = r.cap;
    $('#bfo').innerHTML = `<p class="small" style="margin-bottom:var(--s3)"><b>Read ${r.details_found} details${r.pages ? ` from ${r.pages} pages` : ''}.</b> ${r.missing.length ? `Not stated: ${esc(r.missing.join(', '))}.` : 'Nothing essential is missing.'}</p>`;
  };
  $('#bf').onchange = async e => {
    const file = e.target.files[0];
    if (!file) return;
    $('#bfo').innerHTML = `<div style="margin-bottom:var(--s3)">${working('Reading ' + file.name)}</div>`;
    try {
      if (/\.pdf$/i.test(file.name)) {
        const b64 = btoa(new Uint8Array(await file.arrayBuffer()).reduce((a, c) => a + String.fromCharCode(c), ''));
        showRead(await api('/api/briefs/extract', { filename: file.name, b64 }));
      } else { const text = await file.text(); showRead({ text, ...(await api('/api/briefs/preview', { text })) }); }
    } catch (x) { $('#bfo').innerHTML = `<p class="small" style="margin-bottom:var(--s3);color:var(--err)">${esc(x.message)}</p>`; }
  };
  $('#bs2').onclick = async () => { $('#bfo').innerHTML = `<div style="margin-bottom:var(--s3)">${working('Reading the sample brief')}</div>`; showRead(await api('/api/demo/sample-brief')); };
  $('#rb').onclick = async () => { const b = await api('/api/briefs', { text: $('#brief').value }), f = $('#f').elements; if (b.brand) f.name.value = b.brand; if (b.budget) f.budget.value = b.budget; if (b.niche) f.niche.value = b.niche; if (b.email) { f.sender_email.value = b.email; f.domain.value = /(gmail|yahoo|outlook|hotmail)\./.test(b.email) ? '' : b.email.split('@')[1]; } if (b.sender_name) f.sender_name.value = b.sender_name; $('#rbo').textContent = b.missing.length ? `Still missing: ${b.missing.join(', ')}.` : 'All required fields found.'; };
  $('#f').onsubmit = async e => { e.preventDefault(); const f = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => v !== '')); f.budget = +f.budget; const b = e.target.querySelector('button'); b.disabled = true; $('#st').innerHTML = working('Reading your brief and checking live sources', true); try { const co = await api('/api/companies', f); S.company = co.id; S.role = 'brand'; route(); } catch (x) { b.disabled = false; $('#st').textContent = x.message; } };
}
async function creators() {
  const co = await loadCompany();
  if (!co) { location.hash = '#/home'; return; }
  if (co.status === 'blocked') { view.innerHTML = `<div class="ask bad"><div><h3>Blocked</h3><p class="small">${esc((co.reasons || []).join(' '))}</p></div></div>`; return; }
  const r = await api(`/api/companies/${co.id}/creators`), sel = new Set(r.suggested_bundle);
  view.innerHTML = `<div class="head"><div><h1>Creators for ${esc(co.name)}</h1><p class="muted">Ranked on fit and evidence, not follower count. Merit first, then the published tiebreaks.</p></div><button class="btn b2" id="add">${icon('plus')} Add sample creators</button></div>
  ${r.creators.length ? `<div class="grid g2">${r.creators.map(x => `<article class="card"><div class="row between" style="align-items:flex-start"><div class="row"><div class="avatar sm">${initial(x.handle)}</div><div><h3>@${esc(x.handle)}</h3><p class="cap faint">${esc(x.niche)}${x.is_mock ? ' · <span class="tag">Mock</span>' : ''}</p></div></div><label class="row small" style="gap:6px;cursor:pointer"><input type="checkbox" data-s="${esc(x.creator_id)}" style="width:auto" ${sel.has(x.creator_id) ? 'checked' : ''}> Bundle</label></div>
  <div class="stats3 mt"><div><b class="num">${count(x.followers)}</b><span>Followers</span></div><div><b class="num">${pct(x.engagement_rate)}</b><span>Engagement</span></div><div><b class="num">${money(x.list_price_estimate)}</b><span>Est. per reel</span></div></div>
  <div class="row mt" style="gap:var(--s4)">${meter('Fit', x.fit)}${meter('Confidence', x.confidence, 'c')}</div><p class="whyline">${esc(x.why || '')}</p><details class="ev"><summary>Evidence</summary><ul class="why">${x.reasons.map(t => `<li>${esc(t)}</li>`).join('')}</ul></details>${x.decided_by ? `<p class="tie">Ranked above next: ${esc(x.decided_by)}</p>` : ''}</article>`).join('')}</div><div class="selbar"><span id="sc"></span><button class="btn b3 sm" id="go">Start deal ${icon('arrow')}</button></div>` : `<div class="card empty"><h2>No ${esc(co.niche)} creators yet</h2><p class="muted hero-sub">Add labelled sample creators to try the flow.</p></div>`}
  ${r.failed_gates.length ? `<details class="card flat mt"><summary>${r.failed_gates.length} creators failed safety checks</summary>${r.failed_gates.map(x => `<div class="fact"><b class="small">@${esc(x.handle)}</b><span class="small muted">${esc(x.gates_failed.join(' '))}</span></div>`).join('')}</details>` : ''}`;
  $('#add').onclick = async () => { await api('/api/demo/sample-creators', {}); route(); };
  if (r.creators.length) { const paint = () => { $('#sc').textContent = `${sel.size} selected · budget ${money(r.budget)} stays private`; $('#go').disabled = !sel.size; }; paint(); $$('[data-s]').forEach(x => x.onchange = () => { x.checked ? sel.add(x.dataset.s) : sel.delete(x.dataset.s); paint(); }); $('#go').onclick = () => startDeal([...sel], co.id, { reels: 1, stories: 0, usage_days: 30 }); }
}

/* Deals */
const STAGE = { verify: 'Verify', read_brief: 'Read brief', pitch: 'Pitch', await_company: 'Reply', negotiate: 'Negotiate', contract: 'Contract', recheck: 'Re-check', sign: 'Sign', fund: 'Funds held', deliver: 'Deliver', approve: 'Approve', release: 'Release', invoice: 'Invoice', done: 'Paid' };
const ORDER = Object.keys(STAGE);
function dealList(list, title) {
  if (!list.length) return `<div class="card"><h3>${title}</h3><p class="small faint mt2">No deals yet.</p></div>`;
  return `<div class="card"><h3 style="margin-bottom:var(--s3)">${title}</h3><table class="table"><thead><tr><th>Deal</th><th>Stage</th><th class="r">Brand pays</th><th>Status</th></tr></thead><tbody>${list.slice().reverse().map(d => `<tr class="link" onclick="location.hash='#/deals/${esc(d.id)}'"><td class="mono">${esc(d.id.slice(-6))}</td><td class="small">${esc(STAGE[d.state] || d.state)}</td><td class="r num">${money(d.settlement?.brand_pays)}</td><td>${dealBadge(d)}</td></tr>`).join('')}</tbody></table></div>`;
}
async function deals() {
  const all = await api('/api/deals');
  const list = S.role === 'creator' && S.creator ? all.filter(d => d.creator_ids.includes(S.creator)) : S.role === 'brand' && S.company ? all.filter(d => d.company_id === S.company) : all;
  view.innerHTML = `<div class="head"><div><h1>Deals</h1><p class="muted">Every deal runs until it's paid. Open one to see its evidence and full record.</p></div></div>${dealList(list, 'All deals')}${scenarios(all)}`;
  wireScenarios();
}
function scenarios() {
  return `<div class="card flat mt"><h3>Prove it under pressure</h3><p class="small muted mt2">Each scenario runs a real deal through the real engine, with a simulated failure.</p><div class="row mt3"><button class="btn b2 sm" data-sc="crash">Crash during payment</button><button class="btn b2 sm" data-sc="left">Contact leaves mid-deal</button><button class="btn b2 sm" data-sc="outage">Data source fails</button><span class="small muted" id="sco"></span></div></div>`;
}
function wireScenarios() { $$('[data-sc]').forEach(b => b.onclick = () => runScenario(b.dataset.sc)); }
async function pick() {
  await api('/api/demo/sample-creators', {});
  const cs = await api('/api/creators'), c = cs.find(x => x.id === S.creator) || cs.find(x => x.niche === 'food');
  const cos = await api('/api/companies');
  let co = cos.find(x => x.id === S.company && x.status !== 'blocked' && x.mode === 'simulated');
  if (!co) co = await api('/api/companies', { name: 'Demo Snacks (mock)', niche: c.niche, gstin: '09ABCDE1234F1Z5', budget: 20000 });
  return [c, co];
}
async function runScenario(kind) {
  $('#sco').innerHTML = '<span class="spin"></span> Running…';
  try {
    const [c, co] = await pick(), step = kind === 'crash' ? 'release' : 'contract';
    const d = await api(`/api/deals?crash_after=${step}`, { creator_ids: [c.id], company_id: co.id, terms: { reels: 1, stories: 0, usage_days: 30 }, pace_ms: 300 });
    sessionStorage.scenario = JSON.stringify({ id: d.id, kind, step });
    location.hash = `#/deals/${d.id}`;
  } catch (e) { $('#sco').textContent = e.message; }
}
const EVENTS = { budget_checked: "Checked against the brand's private creator budget", brief_field: e => `Read from the brief: ${e.data.label}`, brief_read: e => `Campaign brief read: ${e.data.fields} details, ${e.data.flags} ${e.data.flags === 1 ? 'flag' : 'flags'}`, signature: 'Contract signed by the company (mock)', terms_compared: e => `Compared ${e.data.count} versions of this deal`, data_call: e => `Crustdata ${e.data.source}: ${e.data.how === 'live' ? `live, ${e.data.seconds}s` : 'from cache'}`, deal_started: 'Deal started', step_done: e => `${STAGE[e.data.step] || e.data.step} finished`, message_queued: e => `Message queued to mock outbox: ${e.data.subject}`, simulated_company_replied: 'Simulated company replied', terms_agreed: e => `Terms agreed at ${money(e.data.price)}`, terms_reduced: 'Requested terms did not fit, so lighter terms were agreed', recheck_passed: 'Pre-signing re-check passed', paused: e => e.data.question || 'Waiting', person_decided: e => `A person answered: ${e.data.approve ? 'yes' : 'no'}`, crashed: e => `Process crashed after ${STAGE[e.data.after] || e.data.after} (simulated)`, blocked: e => `Blocked: ${e.data.reason}`, no_deal: e => `No deal: ${e.data.reason}`, tool_failure: 'A data source failed; the deal is saved', delivery: 'Delivery received', approval: 'Delivery approved', company_response: 'Company responded' };
const KIND = { mock_email: 'Message', contract_issued: 'Contract issued', mock_signature: 'Signature', mock_funds_held: 'Funds held', mock_balance_charged: 'Balance charged', mock_payout: 'Payout', mock_fee: 'Avuno fee', invoice: 'Invoice', exclusivity_reserved: 'Exclusivity reserved' };

async function dealRoom(id) {
  view.innerHTML = spinner('Opening deal…');
  let ctx = null, timer;
  const events = [], seen = {};
  const load = async () => {
    const d = await api(`/api/deals/${id}`);
    if (!ctx) { const [co, cs, full] = await Promise.all([api(`/api/companies/${d.company_id}`), Promise.all(d.creator_ids.map(c => api(`/api/creators/${c}`))), S.role === 'brand' ? api(`/api/companies/${d.company_id}/brief`) : Promise.resolve(null)]); ctx = { co, cs, full }; }
    else if (S.role === 'brand' && !ctx.full?.sha) ctx.full = await api(`/api/companies/${d.company_id}/brief`);
    paintDeal(d, ctx, events);
    wireDeal(d, id, ctx);
    // First paint animates the page. After that, only what changed moves, so the agent's progress is what you notice.
    const lines = [...view.querySelectorAll('.time li, .thread .mail')], rows = [...view.querySelectorAll('.bf-row')], done = [...view.querySelectorAll('.pipe .d i')], attention = d.paused?.kind || d.state;
    if (!seen.first) fx.page(view);
    else {
      fx.fresh(lines.slice(seen.lines));
      fx.fresh(rows.slice(seen.rows));
      fx.grow(done.slice(seen.done));
      if (attention !== seen.attention) fx.arrive(view.querySelector('.ask'));
      if (d.settlement && !seen.price) { const h = view.querySelector('.hero-num'); fx.arrive(h?.closest('.card')); if (h) fx.count(h, 0.1); }
    }
    Object.assign(seen, { first: true, rows: rows.length, lines: lines.length, done: done.length, attention, price: !!d.settlement });
  };
  await load();
  S.es = new EventSource(`/api/deals/${id}/events`);
  S.es.onmessage = m => { events.push(JSON.parse(m.data)); clearTimeout(timer); timer = setTimeout(() => { if (location.hash.includes(id)) load().catch(() => {}); }, 120); };
  S.es.onerror = () => { if (S.es) { S.es.close(); S.es = null; } };
}
function dealBrief(d, full, events) {
  if (full?.sha) {
    const revealed = events.filter(e => e.type === 'brief_field').map(e => e.data.key);
    const reading = !d.brief;
    return briefCard({ ...full, fields: reading ? full.fields.filter(f => revealed.includes(f.key)) : full.fields, flags: reading ? [] : (d.brief.flags || []).concat((full.flags || []).filter(f => f.private)), missing: reading ? [] : full.missing });
  }
  if (d.brief?.is_mock) return briefCard({ ...d.brief, text: null }, { title: 'Campaign brief', note: 'This brand has no brief yet, so a labelled placeholder is used for this simulated deal.' });
  return d.brief ? `<details class="card"><summary>Creator brief</summary><div class="mt3">${creatorDoc(d.brief.creator_brief)}</div></details>` : '';
}
function paintDeal(d, { co, cs, full: ctxFull }, events) {
  const at = ORDER.indexOf(d.state), final = ['blocked', 'no_deal'].includes(d.state), s = d.settlement, t = s?.terms;
  const last = events.filter(e => e.type === 'step_done').pop(); const reached = final ? ORDER.indexOf(last?.data.next || 'verify') : at;
  const crashed = events.some(e => e.type === 'crashed') && !events.slice(events.findIndex(e => e.type === 'crashed') + 1).some(e => e.type === 'step_done');
  const open = view.querySelector('details[data-k]')?.open;
  const pays = (d.actions || []).filter(a => a.kind === 'mock_payout').length;
  view.innerHTML = `<div class="head"><div><p class="cap faint"><a href="#/deals">Deals</a> / ${esc(d.id)}</p><h1 style="margin-top:4px">${esc(co.name)} × ${cs.map(c => '@' + esc(c.handle)).join(', ')}</h1></div>${crashed ? '<span class="badge b-err"><i></i>Crashed</span>' : dealBadge(d)}</div>
  ${liveBar(d, events, crashed, final, co)}<div class="card mt"><div class="pipe">${ORDER.map((x, i) => `<div class="${final && i === reached ? 'x' : i < reached || d.state === 'done' ? 'd' : i === reached ? 'n' : ''}"><i></i>${STAGE[x]}</div>`).join('')}</div></div>
  ${crashed ? `<div class="ask bad mt"><div><h3>The process crashed mid-step</h3><p class="small">Actions may already have run, but the step was not saved. Resuming must not repeat any of them.</p></div><button class="btn b1" id="resume">Resume deal</button></div>` : ''}
  ${d.paused?.question ? `<div class="ask mt"><div><h3>Your answer changes the result</h3><p class="small">${esc(d.paused.question)}</p></div><div class="row"><button class="btn b1 sm" id="yes">Continue</button><button class="btn b2 sm" id="no">Stop deal</button></div></div>` : ''}
  ${d.paused && !d.paused.question ? `<div class="ask mt"><div><h3>${esc({ company_response: 'Waiting for the company', delivery: 'Waiting for delivery', approval: 'Waiting for approval', signature: 'Ready to sign', own_contract: 'Add your contract' }[d.paused.kind] || 'Waiting')}</h3><p class="small">${esc({ company_response: 'The company needs to respond.', delivery: 'The creator posts the content, then marks it delivered.', approval: 'The company reviews the post, then approves it to release payment.', own_contract: 'You chose to use your own contract. Paste it below. It must still cover ad disclosure. The agreed terms are shown on this page.', signature: 'The facts were re-checked just now, and the evidence for each party is below. Read the contract, then sign. This signature is a mock.' }[d.paused.kind] || d.paused.kind)}</p></div>${['company_response', 'own_contract'].includes(d.paused.kind) ? '' : `<button class="btn b1" id="act" data-a="${esc(d.paused.kind)}">${esc({ delivery: 'Mark delivered', approval: 'Approve delivery', signature: 'Sign contract' }[d.paused.kind])}</button>`}</div>` : ''}
  ${d.paused?.kind === 'own_contract' ? `<div class="card mt"><label class="f"><span>Your contract</span><textarea id="ownc" rows="9" placeholder="Paste the full contract text"></textarea></label><button class="btn b1" id="ownsave">Use this contract</button></div>` : ''}
  ${d.final_reason ? `<div class="ask bad mt"><div><h3>${d.state === 'blocked' ? 'Blocked, and nothing was sent' : 'No deal'}</h3><p class="small">${esc(d.final_reason)}</p></div></div>` : ''}
  ${d.state === 'done' ? `<div class="ask mt" style="background:var(--ok-bg);border-color:#C6DACB"><div><h3>Finished: contract signed, money released, invoice issued</h3><p class="small">${pays} payout${pays === 1 ? '' : 's'} made, exactly once${events.some(e => e.type === 'crashed') ? ', even after the crash' : ''}. Payments and signatures are mocks.</p></div></div>` : ''}
  ${d.paused?.kind === 'campaign_brief' ? `<div class="card mt"><h3>This brand needs a campaign brief</h3><p class="small muted mt2">Creators need something to read, and the agent needs something to check. Paste it here to continue.</p><textarea id="dealbrief" rows="8" class="mt3" placeholder="Objective, deliverables, key message, dos and don'ts, timeline"></textarea><button class="btn b1 mt3" id="dealbriefsave">Use this brief</button></div>` : ''}
  <div class="split mt"><div class="stack">
    ${dealBrief(d, ctxFull, events)}
    ${s ? `<div class="card"><p class="small muted">Agreed price</p><div class="hero-num num mt2">${money(s.price)}</div><p class="tie">${esc(s.rule)}</p><div class="mt3"><div class="kv"><span>Brand pays</span><b class="num">${money(s.brand_pays)}</b></div>${Object.entries(s.creator_net).map(([c, n]) => `<div class="kv"><span>@${esc(cs.find(x => x.id === c)?.handle || c)} nets</span><b class="num">${money(n)}</b></div>`).join('')}<div class="kv"><span>Avuno fee (disclosed, 5% each side)</span><b class="num">${money(s.fee_brand + s.fee_creators)}</b></div><div class="kv"><span>Deliverables</span><b>${t.reels} reel, ${t.stories} stories${cs.length > 1 ? ' each' : ''}</b></div><div class="kv"><span>Usage</span><b>${t.usage_days} days${t.paid_ads ? ', paid ads' : ''}</b></div><div class="kv"><span>Exclusivity</span><b>${t.exclusivity_days ? t.exclusivity_days + ' days' : 'None'}</b></div>${d.tier_terms ? `<div class="kv"><span>Held upfront</span><b>${d.tier_terms.upfront_pct}% (${esc(d.tier_terms.label)})</b></div>` : ''}</div>${d.terms_reduced ? `<p class="small mt2">${esc(d.terms_reduced)}</p>` : ''}</div>` : ''}
    <div class="card"><div class="row between"><h3>Who is ${esc(co.name)}?</h3>${verifyBadge(co.status)}</div><ul class="why">${(co.reasons || []).map(r => `<li>${esc(r)}</li>`).join('')}</ul><div class="mt3">${factRows([...(co.facts || []), ...(d.facts || [])])}</div></div>
    ${d.recheck ? `<div class="card"><div class="row between"><h3>Re-check before signing</h3>${d.recheck.changed ? '<span class="badge b-warn"><i></i>Changed</span>' : '<span class="badge b-ok"><i></i>No change</span>'}</div><p class="small muted mt2">${esc(d.recheck.detail)} ${esc(day(d.recheck.at))}</p></div>` : ''}
    ${threadCard(d)}
    ${d.invoice ? `<div class="card" id="invoice"><div class="row between"><h3>Invoice ${esc(d.invoice.number)}</h3><span class="tag">Mock</span></div><div class="mt3"><div class="kv"><span>Bill to</span><b>${esc(d.invoice.bill_to)}</b></div><div class="kv"><span>Creator services</span><b class="num">${money(d.invoice.services)}</b></div><div class="kv"><span>Avuno fee (5%)</span><b class="num">${money(d.invoice.broker_fee)}</b></div><div class="kv"><span>Total</span><b class="num">${money(d.invoice.total)}</b></div></div><p class="cap faint mt2">${esc(d.invoice.tax_note)}</p></div>` : ''}
    ${d.contract_hash ? `<details class="card" data-k ${open ? 'open' : ''}><summary>Contract${d.contract_source ? ` · ${esc(d.contract_source)}` : ''}${d.tracking_code ? ` · Tracking code ${esc(d.tracking_code)}` : ''}</summary><p class="cap faint mt2">SHA-256 <span class="mono">${esc(d.contract_hash)}</span></p><pre class="doc">${esc(d.contract_text)}</pre></details>` : ''}
  </div><div class="stack"><div class="card"><h3 style="margin-bottom:var(--s3)">Activity</h3><ul class="time">${events.length ? events.filter(e => e.type !== 'step_started' && (APP.show_data_calls || e.type !== 'data_call')).map(e => { const m = EVENTS[e.type]; return `<li class="${['crashed', 'blocked', 'no_deal'].includes(e.type) ? 'e' : e.type === 'paused' ? 'w' : ''}">${esc(typeof m === 'function' ? m(e) : m || e.type)}<small>${esc(clock(e.ts))}</small></li>`; }).join('') : '<li class="w">Waiting for the first step…</li>'}</ul></div>
  <div class="card"><div class="row between"><h3>Action ledger</h3><span class="tag">Mock</span></div><p class="cap faint mt2">Each action has a unique key, so it can only happen once.</p><div class="mt2">${(d.actions || []).map(a => `<div class="kv small"><span>${esc(KIND[a.kind] || a.kind)}</span><b class="num">${a.payload.amount != null ? money(a.payload.amount) : a.payload.total != null ? money(a.payload.total) : ''}</b></div>`).join('') || '<p class="faint small">Nothing has happened yet.</p>'}</div></div></div></div>`;
}
function creatorDoc(cb, opts = {}) {
  if (!cb) return '';
  const sec = x => {
    if (x.key === 'must_not') return `<div class="doc-note no"><b>${esc(x.label).toUpperCase()}</b><ul>${x.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`;
    if (x.key === 'disclosure') return `<div class="doc-note ok"><b>${esc(x.label).toUpperCase()}</b><p>${esc(x.items.join(' '))}</p></div>`;
    return `<h4>${esc(x.label)}</h4>${x.items.length > 1 ? `<ul>${x.items.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : `<p>${esc(x.items[0])}</p>`}`;
  };
  return `<article class="doc" aria-label="Creator brief"><div class="doc-top"><b>AVUNO</b> / CREATOR BRIEF</div>${cb.client ? `<div class="doc-client">${esc(cb.client)}</div>` : ''}<h2>${esc(cb.title)}</h2><div class="doc-sub">${opts.note ? esc(opts.note) : "Made from the brand's confidential document. Budget and internal details are removed."}</div>${cb.sections.map(sec).join('')}</article>`;
}
function briefCard(b, opts = {}) {
  if (!b) return '';
  const hits = new Set((b.fields || []).flatMap(f => f.lines || []));
  const doc = b.text ? `<div class="brief-doc" aria-label="Campaign brief text">${b.text.replace(/\r/g, '').split('\n').map((l, i) => `<div class="${hits.has(i) ? 'hit' : ''}">${esc(l) || '&nbsp;'}</div>`).join('')}</div>` : '';
  const rows = (b.fields || []).map(f => `<div class="bf-row ${f.private ? 'priv' : ''}"><b>${esc(f.label)}</b><span>${esc(f.value.length > 170 ? f.value.slice(0, 170) + '…' : f.value)}</span></div>`).join('') || '<p class="small faint">Reading…</p>';
  const flags = (b.flags || []).map(f => `<div class="bf-flag ${esc(f.severity)}">${esc(f.text)}</div>`).join('');
  const missing = b.missing?.length ? `<div class="bf-flag info">Not stated: ${esc(b.missing.join(', '))}.</div>` : '';
  return `<div class="card brief-card"><div class="row between"><h3>${esc(opts.title || 'Campaign brief, as the agent read it')}</h3>${b.is_mock ? '<span class="tag">Placeholder, mock</span>' : b.sha ? `<span class="cap faint mono">${esc(b.version || '')} ${esc(b.sha.slice(0, 12))}</span>` : ''}</div><p class="small muted mt2">${esc(opts.note || 'Confidential to the brand. Each detail on the right comes from a highlighted line.')}</p><div class="brief"><div>${doc}</div><div>${rows}${missing}${flags}</div></div>${opts.after || ''}</div>`;
}
function questionsCard(b) {
  if (!b?.open_questions?.length) return '';
  return `<div class="card"><h3>Open questions in your brief</h3><p class="small muted mt2">Unanswered in your document. These are proposed defaults, and none are assumed silently.</p><div class="mt3">${b.open_questions.map(q => `<div class="q-row"><b>${esc(q.id)}. ${esc(q.question)}</b><small>Proposed: ${esc(q.default)}</small></div>`).join('')}</div></div>`;
}
function threadCard(d) {
  const mails = d.thread || [];
  if (!mails.length) return '';
  const last = mails[mails.length - 1].day;
  return `<div class="card"><div class="row between"><h3>Email thread</h3><span class="tag">Mock</span></div><p class="small muted mt2">So far this is about <b>${last} ${last === 1 ? 'day' : 'days'}</b> of email in a real deal (our estimate), compressed here. Nothing reaches anyone real, and replies from the other side are simulated.</p><div class="thread mt3">${mails.map(m => `<details class="mail ${m.from === 'Avuno' ? 'out' : 'in'}"><summary><span class="daychip">Day ${m.day}</span><span class="mail-who">${esc(m.from)}</span><span class="mail-sub">${esc(m.subject)}</span>${m.simulated_reply ? '<span class="tag">Simulated</span>' : ''}</summary><p class="cap faint mt2">To ${esc(m.to)}</p><p class="small mt2" style="white-space:pre-wrap">${esc(m.body)}</p></details>`).join('')}</div></div>`;
}
const STEP_TEXT = { verify: ['Checking the company and pulling its current data', 1], read_brief: ['Reading the campaign brief line by line and checking it against the rules', 0], pitch: ['Emailing the pitch to the person found on Crustdata (mock outbox)', 0], await_company: ['Waiting for the company\'s reply', 0], negotiate: ['Negotiating by email, comparing versions of the deal within both private limits', 0], contract: ['Drafting the contract and sealing it with a hash', 0], recheck: ['Re-checking the facts live before anyone signs', 1], sign: ['Collecting signatures', 0], fund: ['Holding funds (mock)', 0], deliver: ['Waiting for delivery', 0], approve: ['Waiting for approval', 0], release: ['Releasing money to each party, exactly once (mock)', 0], invoice: ['Issuing the invoice', 0] };
function liveBar(d, events, crashed, final, co) {
  if (final || crashed || d.paused || d.state === 'done') return '';
  const [text, isLookup] = STEP_TEXT[d.state] || ['Working', 0];
  const live = isLookup && (co?.domain || co?.company_id);      // Only claim a lookup when one can actually happen.
  const last = [...events].reverse().find(e => e.type === 'data_call');
  return `<div class="card">${working(text, live)}${live && last ? `<p class="cap faint mt2">Latest lookup: ${esc(last.data.source)}, ${last.data.how === 'live' ? `live in ${last.data.seconds}s` : 'from cache'}</p>` : ''}${d.pace_ms ? '<p class="cap faint mt2">Steps are slowed so you can follow them. Change this in Settings.</p>' : ''}</div>`;
}
function wireDeal(d, id) {
  if ($('#dealbriefsave')) $('#dealbriefsave').onclick = async () => { try { await api(`/api/deals/${id}/brief`, { text: $('#dealbrief').value }); route(); } catch (e) { toast(e.message); } };
  if ($('#ownsave')) $('#ownsave').onclick = async () => { try { await api(`/api/deals/${id}/own-contract`, { text: $('#ownc').value }); route(); } catch (e) { toast(e.message); } };
  if ($('#act')) $('#act').onclick = async () => { await api(`/api/deals/${id}/${{ delivery: 'deliver', approval: 'approve', signature: 'sign' }[$('#act').dataset.a]}`, $('#act').dataset.a === 'delivery' ? [] : {}); route(); };
  const answer = async ok => { await api(`/api/deals/${id}/decide`, { approve: ok }); route(); };
  if ($('#yes')) { $('#yes').onclick = () => answer(true); $('#no').onclick = () => answer(false); }
  if ($('#resume')) $('#resume').onclick = async () => {
    const sc = JSON.parse(sessionStorage.scenario || 'null');
    if (sc?.id === id && sc.kind === 'left') await api(`/api/demo/deals/${id}/contact-left`, {});
    if (sc?.id === id && sc.kind === 'outage') await api(`/api/demo/deals/${id}/outage`, {});
    await api(`/api/deals/${id}/resume`, {}); route();
  };
}

/* Messages */
async function messages() {
  const all = (await api('/api/outbox')).filter(a => a.kind === 'mock_email').reverse();
  view.innerHTML = `<div class="head"><div><h1>Messages</h1><p class="muted">The agent's outgoing messages. This is a mock outbox: nothing reaches real people.</p></div><span class="tag">Mock outbox</span></div>
  ${all.length ? `<div class="stack">${all.map(a => `<details class="card"><summary>${esc(a.payload.subject)}</summary><p class="cap faint mt2">To ${esc(a.payload.to)} · ${esc(day(a.ts))} ${esc(clock(a.ts))}</p><p class="small mt2" style="white-space:pre-wrap">${esc(a.payload.body)}</p></details>`).join('')}</div>` : '<div class="card empty"><h2>Nothing sent yet</h2><p class="muted mt2">Messages appear here once a deal starts.</p></div>'}`;
}

/* Read progress */
async function watchRead(id, el) {
  for (let i = 0; i < 300; i++) {
    const c = await api(`/api/creators/${id}`);
    if (c.status !== 'reading') return c;
    el.innerHTML = working(c.progress || 'Starting', true);
    await new Promise(r => setTimeout(r, 700));
  }
}

/* Applications, for creators */
const APP_STATUS = { sent: ['b-info', 'Waiting for the brand'], accepted: ['b-ok', 'Accepted'], declined: ['b-none', 'Passed'] };
async function applicationsPage() {
  if (!S.creator) { location.hash = '#/home'; return; }
  const [list, st] = await Promise.all([api(`/api/creators/${S.creator}/applications`), api(`/api/settings/creator/${S.creator}`)]);
  view.innerHTML = `<div class="head"><div><h1>Applications</h1><p class="muted">${st.auto_deal ? 'Auto Deal is on, so eligible brands get your Standard pack automatically.' : 'Packs you have sent to brands.'}</p></div><a class="btn b1" href="#/brands">Find brands ${icon('arrow')}</a></div>
  ${list.length ? `<div class="stack">${list.map(a => { const [c, l] = APP_STATUS[a.status]; return `<article class="card"><div class="row between"><div><h3>${esc(a.company_name)}</h3><p class="cap faint">${esc(a.pack)} pack · ${a.terms.reels} reel, ${a.terms.stories} stories, ${a.terms.usage_days} days usage${a.source === 'auto' ? ' · <span class="tag">Sent by Auto Deal</span>' : ''}${a.brief_sha ? ' · Brief available' : ' · No brief yet'}</p></div><span class="badge ${c}"><i></i>${l}</span></div><p class="whyline">${esc(a.why_brand)}</p>${a.note ? `<p class="small muted mt2">${esc(a.note)}</p>` : ''}${a.deal_id ? `<a class="btn b2 sm mt3" href="#/deals/${esc(a.deal_id)}">Open deal ${icon('arrow')}</a>` : ''}</article>`; }).join('')}</div>` : '<div class="card empty"><h2>Nothing sent yet</h2><p class="muted mt2">Open a brand\'s media packs and apply, or turn on Auto Deal.</p></div>'}`;
}

/* Offers, for brands */
async function offersPage() {
  const co = await loadCompany();
  if (!co) { location.hash = '#/home'; return; }
  const r = await api(`/api/companies/${co.id}/applications`);
  view.innerHTML = `<div class="head"><div><h1>Offers for ${esc(co.name)}</h1><p class="muted">Ranked on fit and evidence, not follower count. Your budget stays private, and so do their limits.${r.hidden ? ` ${r.hidden} below your minimum fit ${r.hidden === 1 ? 'is' : 'are'} hidden.` : ''}</p></div></div>
  ${co.brief ? '' : `<div class="ask" style="margin-bottom:var(--s4)"><div><h3>Add your campaign brief first</h3><p class="small">You can't choose a creator until they have something to read.</p></div><a class="btn b1" href="#/home">Add brief</a></div>`}
  ${r.open.length ? `<div class="stack">${r.open.map(x => `<article class="card"><div class="row between" style="align-items:flex-start"><div class="row"><div class="avatar sm">${initial(x.handle)}</div><div><h3>${x.rank}. @${esc(x.handle)}</h3><p class="cap faint">${esc(x.niche)}${x.is_mock ? ' · <span class="tag">Mock</span>' : ''}${x.source === 'auto' ? ' · Sent by Auto Deal' : ''}</p></div></div><div class="row"><button class="btn b2 sm" data-no="${esc(x.id)}">Pass</button><button class="btn b1 sm" data-yes="${esc(x.id)}" ${co.brief ? '' : 'disabled'}>Choose ${icon('arrow')}</button></div></div>
  <div class="stats3 mt"><div><b class="num">${count(x.followers)}</b><span>Followers</span></div><div><b class="num">${pct(x.engagement_rate)}</b><span>Engagement</span></div><div><b class="num">${money(x.list_price_estimate)}</b><span>Est. price</span></div></div>
  <p class="small muted mt3">${esc(x.pack)} pack: ${x.terms.reels} reel, ${x.terms.stories} stories, ${x.terms.usage_days} days usage${x.terms.exclusivity_days ? `, ${x.terms.exclusivity_days} days exclusive` : ''}</p>
  <div class="row mt" style="gap:var(--s4)">${meter('Fit', x.fit)}${meter('Confidence', x.confidence, 'c')}</div>${x.brief_checks?.length ? `<div class="checks" aria-label="Checked against your brief">${x.brief_checks.map(c => `<span class="check ${esc(c.status)}">${{ pass: '✓', partial: '~', fail: '✕', unknown: '?' }[c.status]} ${esc(c.label)}: ${esc(c.detail)}</span>`).join('')}</div>` : ''}<p class="whyline">${esc(x.why)}</p><details class="ev"><summary>Evidence</summary><ul class="why">${x.reasons.map(t => `<li>${esc(t)}</li>`).join('')}</ul></details>${x.decided_by ? `<p class="tie">Ranked above next: ${esc(x.decided_by)}</p>` : ''}</article>`).join('')}</div>` : '<div class="card empty"><h2>No open offers</h2><p class="muted mt2">When creators apply to you, they appear here ranked.</p></div>'}
  ${r.closed.length ? `<details class="card flat mt"><summary>${r.closed.length} closed</summary>${r.closed.map(a => `<div class="fact"><b class="small">@${esc(a.handle)}</b><span class="small muted">${esc(APP_STATUS[a.status][1])}</span></div>`).join('')}</details>` : ''}`;
  $$('[data-yes]').forEach(b => b.onclick = async () => { b.disabled = true; try { const d = await api(`/api/applications/${b.dataset.yes}/accept`, {}); location.hash = `#/deals/${d.id}`; } catch (e) { b.disabled = false; toast(e.message); } });
  $$('[data-no]').forEach(b => b.onclick = async () => { await api(`/api/applications/${b.dataset.no}/decline`, {}); route(); });
}

/* Settings. Every control here changes real behaviour. */
const SETTINGS = {
  creator: ['Creator', [
    ['#', 'Auto Deal'],
    ['auto_deal', 'Auto Deal', 'Send a media pack to every brand that clears the bars below. Brands still choose; nothing is signed without them.'],
    ['auto_pack', 'Pack to send', 'Which of your media packs goes out.', ['Starter', 'Standard', 'Campaign']],
    ['auto_min_likelihood', 'Minimum likelihood', 'How likely a brand is to buy. Brands need 45 just to be shown.', 0, 100],
    ['auto_min_confidence', 'Minimum confidence', 'How much evidence backs that score.', 0, 100],
    ['auto_max_per_run', 'Most applications to send', 'A cap, so nothing goes out in bulk by accident.', 1, 50],
    ['auto_allow_partly_verified', 'Include partly verified brands', 'Brands with less public evidence. Money is always held upfront for them.'],
  ]],
  company: ['Brand', [
    ['#', 'Campaign'],
    ['campaign_goal', 'Campaign goal', 'Changes what creator fit weighs. Conversion favours audience match; engagement favours attention.', ['balanced', 'awareness', 'engagement', 'conversion', 'brand_building']],
    ['#', 'Contracts'],
    ['write_contracts', 'Write contracts for me', 'Avuno drafts the contract. Turn off to supply your own; it must still cover ad disclosure.'],
    ['clause_kill_fee', 'Include a kill fee clause', 'The creator keeps the amount held for work done if you cancel.'],
    ['clause_arbitration', 'Use online arbitration for disputes', 'Turn off to name the courts instead.'],
    ['sign_myself', 'Sign contracts myself', 'Pause for you to sign, instead of a mock signature.'],
    ['#', 'Choosing creators'],
    ['decline_others_on_choose', 'Close other applications when I choose', 'Turn off to work with several creators on one campaign.'],
    ['offers_min_fit', 'Hide offers below this fit', 'Hidden offers are counted, not deleted. 0 shows everything.', 0, 100],
    ['auto_accept', 'Auto-accept strong applications', 'Choose any creator who clears the fit score below.'],
    ['auto_accept_min_fit', 'Minimum fit to auto-accept', 'Out of 100.', 0, 100],
    ['#', 'Deals'],
    ['allow_lighter_terms', 'Allow lighter terms', 'If your requested terms do not fit, try a lighter version. Turn off to be asked instead.'],
    ['simulate_delivery', 'Simulate delivery and approval', 'Skip waiting for a real post. Labelled as mock.'],
  ]],
  app: ['Display', [
    ['motion', 'Animations', 'Auto follows your device setting. Full always animates.', ['auto', 'full', 'off']],
    ['compact', 'Compact layout', 'Fit more on the screen.'],
    ['show_why', 'Show "why" lines', 'The one-line reason on each brand and creator.'],
    ['show_evidence', 'Show evidence', 'The cited facts behind each score.'],
    ['show_tiebreaks', 'Show tiebreak reasons', 'Which rule decided the ranking.'],
    ['show_fetching', 'Show the "Fetching from Crustdata" chip', 'The progress bar stays either way.'],
    ['show_data_calls', 'Show every data lookup', 'Lists each Crustdata lookup in the deal activity.'],
    ['#', 'Pace and AI'],
    ['watchable_pace', 'Watchable pace', 'Slows deal steps so people can follow them. The deal page says so while it is on.'],
    ['pace_ms', 'Pause per step (ms)', 'Applies to deals started after this change.', 0, 3000],
    ['ai_pitch_polish', 'Polish pitches with AI', 'Needs an API key, and uses tokens. Without a key, the template pitch is used.'],
  ]],
};
function applyPrefs() {
  const c = document.body.classList;
  c.toggle('compact', !!APP.compact); c.toggle('hide-why', APP.show_why === false); c.toggle('hide-evidence', APP.show_evidence === false); c.toggle('hide-tie', APP.show_tiebreaks === false); c.toggle('hide-fetching', APP.show_fetching === false);
  fx.setLevel(APP.motion || 'auto');
}
function settingRow(s, [k, l, h, a, b], vals) {
  if (k === '#') return `<div class="setgroup">${esc(l)}</div>`;
  const v = vals[k];
  const control = typeof v === 'boolean' ? `<label class="switch"><input type="checkbox" data-s="${s}" data-k="${k}" aria-label="${esc(l)}" ${v ? 'checked' : ''}><span></span></label>`
    : Array.isArray(a) ? `<select data-s="${s}" data-k="${k}" aria-label="${esc(l)}">${a.map(o => `<option value="${o}" ${o === v ? 'selected' : ''}>${(o[0].toUpperCase() + o.slice(1)).replace('_', ' ')}</option>`).join('')}</select>`
    : `<input type="number" data-s="${s}" data-k="${k}" min="${a}" max="${b}" value="${v}" aria-label="${esc(l)}">`;
  return `<div class="setrow"><div><b class="small">${esc(l)}</b><small>${esc(h)}</small></div>${control}</div>`;
}
async function settingsPage() {
  const scopes = [S.role === 'creator' && S.creator ? ['creator', S.creator] : null, S.role === 'brand' && S.company ? ['company', S.company] : null, ['app', 'global']].filter(Boolean);
  const vals = await Promise.all(scopes.map(([s, i]) => api(`/api/settings/${s}/${i}`)));
  const lim = S.role === 'creator' && S.creator ? await api(`/api/creators/${S.creator}/limits`) : null;
  const limits = lim ? `<section class="card"><h3 style="margin-bottom:var(--s2)">My limits</h3><p class="small muted" style="margin-bottom:var(--s2)">Private. Brands never see these, and no deal goes below them.</p>
    <div class="setrow"><div><b class="small">Lowest price per reel (₹)</b><small>Blank uses our estimate.</small></div><input type="number" min="0" id="l-floor_reel" value="${lim.floor_reel ?? ''}" aria-label="Lowest price per reel"></div>
    <div class="setrow"><div><b class="small">Lowest price per story (₹)</b><small>Blank uses a third of the reel price.</small></div><input type="number" min="0" id="l-floor_story" value="${lim.floor_story ?? ''}" aria-label="Lowest price per story"></div>
    <div class="setrow"><div><b class="small">Longest exclusivity (days)</b><small>Packs above this are refused.</small></div><input type="number" min="0" max="365" id="l-max_exclusivity_days" value="${lim.max_exclusivity_days}" aria-label="Longest exclusivity"></div>
    <div class="setrow"><div><b class="small">Allow paid ads with my content</b><small>Brands pay more for this.</small></div><label class="switch"><input type="checkbox" id="l-allow_paid_ads" ${lim.allow_paid_ads ? 'checked' : ''} aria-label="Allow paid ads"><span></span></label></div>
    <div class="setrow"><div><b class="small">Brands I won't work with</b><small>Types of business, separated by commas.</small></div><input type="text" id="l-blocked_categories" value="${esc((lim.blocked_categories || []).join(', '))}" placeholder="e.g. betting, crypto" aria-label="Brands I will not work with"></div></section>` : '';
  const quiet = fx.reduced() && APP.motion === 'auto' ? '<p class="small muted" style="margin-top:var(--s2)">Your device asks for reduced motion, so animations are off. Choose Full to turn them on here.</p>' : '';
  view.innerHTML = `<div class="head"><div><h1>Settings</h1><p class="muted">Saved as soon as you change them. Core safety checks are always on: impersonation blocking, the re-check before signing, private limits and ad disclosure.</p></div></div><div class="stack" style="max-width:780px">${limits}${scopes.map(([s], n) => `<section class="card"><h3 style="margin-bottom:var(--s2)">${SETTINGS[s][0]}</h3>${SETTINGS[s][1].map(r => settingRow(s, r, vals[n])).join('')}${s === 'app' ? quiet : ''}</section>`).join('')}</div>`;
  $$('[data-k]').forEach(x => x.onchange = async () => {
    const id = scopes.find(([s]) => s === x.dataset.s)[1], value = x.type === 'checkbox' ? x.checked : x.tagName === 'SELECT' ? x.value : +x.value;
    try { await api(`/api/settings/${x.dataset.s}/${id}`, { [x.dataset.k]: value }); if (x.dataset.s === 'app') { APP[x.dataset.k] = value; applyPrefs(); if (x.dataset.k === 'motion' && value !== 'off') fx.page(view); } toast(x.dataset.k === 'auto_deal' && value ? 'Auto Deal is on. Packs are going out to eligible brands.' : 'Saved.'); }
    catch (e) { toast(e.message); route(); }
  });
  if (lim) $$('[id^="l-"]').forEach(x => x.onchange = async () => {
    const num = id => { const v = $(id).value; return v === '' ? null : +v; };
    const body = { floor_reel: num('#l-floor_reel'), floor_story: num('#l-floor_story'), max_exclusivity_days: num('#l-max_exclusivity_days') ?? 0, allow_paid_ads: $('#l-allow_paid_ads').checked, blocked_categories: $('#l-blocked_categories').value.split(',').map(t => t.trim()).filter(Boolean) };
    try { await api(`/api/creators/${S.creator}/limits`, body); toast('Saved. These stay private.'); } catch (e) { toast(e.message); }
  });
}

nav(); foot(); api('/api/settings/app/global').then(a => { APP = a; }).catch(() => {}).finally(() => { applyPrefs(); fx.logo(); route(); });
