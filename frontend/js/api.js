/* Live mode: connects the UI to the Agent Bank backend (REST + WebSocket).
   Loaded after app.js. If your field names or routes differ, edit MAP and the g(...) alias lists below. */
(function () {
  const C = window.AB_CONFIG || {};
  if (!(C.LIVE || /[?&]live=1/.test(location.search))) return;
  const API = (C.API || 'http://localhost:8000').replace(/\/$/, '');
  const WSU = C.WS || API.replace(/^http/, 'ws') + '/ws';

  const MAP = {
    state: '/state',
    fund: id => `/agents/${id}/fund`, withdraw: id => `/agents/${id}/withdraw`,
    newJob: '/jobs', newAgent: '/agents', cheater: '/demo/cheater', demo: '/demo/start',
    fundBody: n => ({ amount: n }), withdrawBody: n => ({ amount: n }),
    jobBody: f => ({ title: f.title, description: f.desc, budget: f.budget, skill: f.skill, acceptance_criteria: f.crit, manager_id: f.manager }),
    agentBody: f => ({ name: f.name, skill: f.skill, role: 'worker' })
  };

  const g = (o, ...k) => { for (const x of k) if (o && o[x] !== undefined && o[x] !== null) return o[x]; };
  const num = v => +v || 0;
  const cid = v => String(v && typeof v === 'object' ? g(v, 'id', 'agent_id', 'uuid') : v).replace(/[^\w-]/g, '');
  const STAGE = { open: 0, bidding: 0, posted: 0, created: 0, awarded: 1, escrowed: 1, funded: 1, locked: 1, in_progress: 2, working: 2, started: 2, delivered: 3, verifying: 3, pending_verification: 3, paid: 4, completed: 4, released: 4, verified: 4, refunded: 5, failed: 5, rejected: 5, cancelled: 5, canceled: 5, expired: 5 };
  const stage = s => STAGE[String(s || '').toLowerCase()] ?? 0;
  const clk = v => { const d = v ? new Date(v) : new Date(); return isNaN(d) ? clock() : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }); };

  const cache = {}; let reconciled = true, online = null, hs = null;
  bal = () => reconciled;
  $('#pp').style.display = 'none'; $('#sp').style.display = 'none';
  const pill = document.querySelector('.pill'); if (pill) pill.textContent = 'Live backend';

  async function req(path, method = 'GET', body) {
    const r = await fetch(API + path, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    if (!r.ok) throw new Error(method + ' ' + path + ' failed (' + r.status + ')');
    return r.status === 204 ? null : r.json();
  }
  function skillOf(x) { if (!(x in T)) { T[x] = ['Custom task']; RG[x] = [5, 40]; SKC[x] = COLS[Object.keys(SKC).length % COLS.length]; } return x; }

  function upsert(a) {
    const id = cid(a), raw = String(g(a, 'role', 'type', 'kind') || ''), kind = /manager|poster|hirer/i.test(raw) || g(a, 'is_manager') ? 'm' : 'w';
    let skill = g(a, 'skill', 'specialty', 'category') || (/manager|worker|agent/i.test(raw) ? '' : raw) || (kind === 'm' ? 'Operations' : 'General');
    skill = kind === 'm' ? skill : skillOf(skill);
    let rep = num(g(a, 'reputation', 'rep', 'rating', 'trust_score', 'trust')); if (rep > 1) rep /= 100; if (!rep) rep = .8;
    const x = cache[id] || (cache[id] = mk(g(a, 'name', 'display_name') || 'Agent ' + id, skill, kind, 0, rep));
    Object.assign(x, { id, name: g(a, 'name', 'display_name') || x.name, role: skill, kind, bal: num(g(a, 'balance', 'bal', 'wallet_balance')), rep,
      earned: num(g(a, 'earned', 'total_earned', 'earnings')), spent: num(g(a, 'spent', 'total_spent')), jobs: num(g(a, 'jobs_completed', 'completed_jobs', 'jobs')),
      cheat: !!g(a, 'is_malicious', 'malicious', 'cheater'), wal: g(a, 'wallet_id', 'wallet') || x.wal });
    return x;
  }
  const byId = v => (v === undefined || v === null || v === '') ? undefined : cache[cid(v)];

  function verdictOf(j) {
    const v = g(j, 'verdict', 'verification', 'verifier_result', 'verifier'); if (!v) return null;
    if (Array.isArray(v)) return v.map(x => typeof x === 'string' ? x : (g(x, 'check', 'name', 'rule') || 'Check') + ': ' + (g(x, 'passed', 'ok') ? 'pass' : 'fail'));
    if (typeof v === 'string') return [v];
    const lines = []; const sm = g(v, 'summary', 'reason', 'feedback', 'verdict'); if (sm) lines.push(String(sm));
    const ps = g(v, 'passed', 'approved', 'ok'); if (ps !== undefined) lines.push('Verifier result: ' + (ps ? 'pass' : 'fail'));
    const sc = g(v, 'score', 'rubric_score'); if (sc !== undefined) lines.push('Judge score: ' + sc);
    return lines.length ? lines : null;
  }

  function normJob(j) {
    const st = String(g(j, 'status', 'state') || ''), s = stage(st), w = byId(g(j, 'winner_id', 'worker_id', 'assignee_id', 'winner', 'assigned_to'));
    const b = (g(j, 'bids') || []).map(x => ({ w: byId(g(x, 'agent_id', 'worker_id', 'bidder_id', 'agent')), p: num(g(x, 'price', 'amount')), eta: num(g(x, 'eta', 'eta_minutes')) || 3 })).filter(x => x.w);
    const price = num(g(j, 'price', 'awarded_price', 'escrow_amount', 'winning_bid')) || (w && b.find(x => x.w === w) ? b.find(x => x.w === w).p : 0);
    const sub = g(j, 'subcontract', 'sub'); const sw = sub && byId(g(sub, 'agent_id', 'worker_id'));
    let ev = g(j, 'events', 'timeline', 'history');
    ev = Array.isArray(ev) ? ev.map(e => [clk(g(e, 'time', 'created_at', 'timestamp')), g(e, 'text', 'message', 'description', 'type', 'event') || '']) : [[clk(g(j, 'created_at')), 'Job posted. Status: ' + (st || 'open')]];
    return { id: g(j, 'id', 'job_id'), title: g(j, 'title', 'name') || 'Untitled job', skill: skillOf(g(j, 'skill', 'category') || 'General'), budget: num(g(j, 'budget', 'max_budget', 'budget_cap')),
      desc: g(j, 'description', 'desc') || '', crit: g(j, 'acceptance_criteria', 'criteria') || 'See job description.', m: byId(g(j, 'manager_id', 'poster_id', 'creator_id', 'manager')) || mgrs[0],
      stage: s, t: 0, bids: b, w, price: price || num(g(j, 'budget', 'max_budget')), end: 0, res: s === 4 ? 'Paid' : s === 5 ? (/refund|fail|reject/i.test(st) ? 'Refunded' : 'No bids') : '',
      tries: 0, ev, fraud: false, sub: sw ? { w: sw, amt: num(g(sub, 'amount', 'price')) } : null, verdict: verdictOf(j), raw: j };
  }

  function applyState(s) {
    (g(s, 'agents') || []).forEach(upsert);
    const A = Object.values(cache), ids = new Set((g(s, 'agents') || []).map(cid));
    mgrs.length = 0; works.length = 0;
    A.filter(a => ids.has(a.id)).forEach(a => (a.kind === 'm' ? mgrs : works).push(a));
    jobs = (g(s, 'jobs') || []).map(normJob).filter(j => j.id !== undefined && j.m).sort((a, b) => String(b.id).localeCompare(String(a.id), undefined, { numeric: true }));
    let rank = 0; jobs.forEach(j => { if (j.stage >= 4) j.end = rank++; });
    const st = g(s, 'stats', 'totals') || {}, ok = jobs.filter(j => j.res === 'Paid'), rf = jobs.filter(j => j.res === 'Refunded');
    const fee = x => num(g(x.raw, 'fee', 'platform_fee')) || +(x.price * .03).toFixed(2);
    fees = num(g(st, 'fees', 'total_fees', 'platform_fees')) || ok.reduce((a, x) => a + fee(x), 0);
    paid = num(g(st, 'paid', 'total_paid')) || ok.reduce((a, x) => a + x.price - fee(x), 0);
    done = num(g(st, 'jobs_paid', 'completed', 'done')) || ok.length; vtot = num(g(st, 'volume', 'total_volume')) || ok.reduce((a, x) => a + x.price, 0);
    vOk = ok.length; vNo = rf.length + jobs.filter(j => /reject|retry/i.test(String(g(j.raw, 'status') || ''))).length;
    const rc = g(s, 'reconciled', 'ledger_balanced', 'balanced'); reconciled = rc === undefined ? true : !!rc;
    const L = g(s, 'ledger', 'transactions'); if (Array.isArray(L)) led = L.map(e => { const ty = String(g(e, 'type', 'kind') || ''), amt = num(g(e, 'amount')); return { t: clk(g(e, 'created_at', 'time')), text: g(e, 'description', 'memo', 'text') || ty, amt: Math.abs(amt), cls: /release|payout|credit|earn/i.test(ty) ? 'pos' : /refund/i.test(ty) ? 'neg' : 'neu', who: [byId(g(e, 'agent_id', 'from', 'from_agent_id', 'to', 'to_agent_id'))?.name].filter(Boolean) }; }).reverse().slice(0, 150);
    hist.push(paid); if (hist.length > 80) hist.shift(); render(0);
  }

  function refresh() { clearTimeout(hs); hs = setTimeout(() => req(MAP.state).then(s => { if (online !== true) { online = true; toast('Live: connected to backend', 'var(--grn)'); } applyState(s); }).catch(() => { if (online !== false) { online = false; toast('Backend unreachable. Check the API URL and CORS.', 'var(--red)', 200); } }), 150); }

  function onEvent(m) {
    const ty = String(g(m, 'type', 'event', 'kind') || ''), d = g(m, 'data', 'payload') || m, amt = num(g(d, 'amount', 'price', 'net')), a = byId(g(d, 'worker_id', 'agent_id', 'winner_id', 'bidder_id')), nm = g(d, 'worker_name', 'agent_name') || (a && a.name) || 'An agent', title = g(d, 'title', 'job_title') || 'a job';
    if (/released/.test(ty)) { log('Verified. ' + nm + ' paid for “' + title + '”', amt, 'pos', [nm]); toast(nm + ' earned ' + M$(amt), 'var(--grn)', 660); }
    else if (/refund/.test(ty)) { log('Refunded after failed delivery by ' + nm, amt, 'neg', [nm]); toast('Refunded ' + M$(amt), 'var(--red)', 200); }
    else if (/awarded/.test(ty)) log('Escrow locked for ' + nm + ': “' + title + '”', -amt, 'neu', [nm]);
    else if (/bid/.test(ty)) log(nm + ' bid ' + M$(amt) + ' on “' + title + '”', 0, 'neu', [nm]);
    else if (/created/.test(ty)) log('New job posted: “' + title + '”', amt, 'neu');
  }
  function connect() { let w; try { w = new WebSocket(WSU); } catch (e) { return; }
    w.onmessage = e => { try { onEvent(JSON.parse(e.data)); } catch (x) {} refresh(); };
    w.onclose = () => setTimeout(connect, 2500); }

  const fail = e => toast(e.message, 'var(--red)', 200);
  window.fund = async function () { const a = all().find(x => x.id === $('#fa').value), n = Math.max(1, +$('#fm').value || 0);
    try { const r = await req(MAP.fund(a.id), 'POST', MAP.fundBody(n)), u = g(r || {}, 'approve_url', 'approval_url', 'redirect_url', 'checkout_url'); if (u) window.open(u, '_blank'); toast(u ? 'Approve the payment in PayPal' : M$(n) + ' added to ' + a.name, 'var(--sky)', 600); refresh(); } catch (e) { fail(e); } };
  window.settle = async function (id) { const a = all().find(x => x.id === id), n = +Math.max(0, a.bal - 5).toFixed(2); if (n < 1) return toast('Keep at least $5 plus $1 to settle', 'var(--yel)', 300);
    try { await req(MAP.withdraw(a.id), 'POST', MAP.withdrawBody(n)); toast(a.name + ' settled ' + M$(n), 'var(--lime)', 700); refresh(); } catch (e) { fail(e); } };
  window.hire = async function () { const d = $('#jd').value.trim(), f = { title: d ? d.slice(0, 44) : 'Custom job', desc: d || 'Custom job', budget: +$('#jb').value || 20, skill: $('#js').value, crit: $('#jc').value || '', manager: (mgrs[0] || {}).id };
    try { const r = await req(MAP.newJob, 'POST', MAP.jobBody(f)); toast('Job posted: bids are coming in', 'var(--pink)', 500); const id = g(r || {}, 'id', 'job_id'); await new Promise(res => { refresh(); setTimeout(res, 600); }); if (id !== undefined) location.hash = 'job-' + id; } catch (e) { fail(e); } };
  window.reg = async function () { const n = $('#rn').value.trim(); if (!n) return toast('Give the agent a name', 'var(--yel)', 300);
    try { await req(MAP.newAgent, 'POST', MAP.agentBody({ name: n, skill: $('#rs').value })); toast(n + ' joined the market', 'var(--lime)', 600); refresh(); } catch (e) { fail(e); } };
  const demoCall = (p, msg) => async function () { try { await req(p, 'POST', {}); toast(msg, 'var(--yel)', 400); refresh(); } catch (e) { toast(e.message + '. Set MAP.cheater / MAP.demo in api.js.', 'var(--red)', 200); } };
  window.cheat = demoCall(MAP.cheater, 'A cheater is bidding. Watch the verifier.'); window.demo = demoCall(MAP.demo, 'Demo started.');

  render(1); refresh(); connect(); setInterval(refresh, 5000);
})();