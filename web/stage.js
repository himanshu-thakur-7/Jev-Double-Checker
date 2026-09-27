// Double Take stage: replays cached cross-examinations and runs new ones live.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const rs = (x) => "₹" + Math.round(x || 0).toLocaleString("en-IN");
const usd = (x, d = 3) => "$" + (x || 0).toFixed(d);
const MODES = ["jev_only", "jev_llm", "double_take"];
const MODE_NAME = { jev_only: "Jev only", jev_llm: "Jev + LLM", double_take: "Double Take" };
const ACT = { pay: "Pay", hold: "Hold", ignore: "Skip" };

const st = {
  mode: "double_take", msgs: [], ex: {}, shown: 0, sel: null, playing: false, speed: 1, timer: null,
  tab: "cx", gate: [], agent: null, billers: {},
};

function minutes(t) {
  const m = /(\d+):(\d+)\s*(AM|PM)/i.exec(t || "");
  if (!m) return 99999;
  let h = +m[1] % 12; if (m[3].toUpperCase() === "PM") h += 12;
  return h * 60 + +m[2];
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

async function load() {
  const data = await api("/api/messages");
  st.msgs = data.messages.filter((m) => m.set !== "custom").sort((a, b) => minutes(a.time) - minutes(b.time));
  $("#set-name").textContent = `Gold set + hero candidates (${data.count})`;
  $("#set-progress").style.width = `${(100 * data.cached) / data.count}%`;
  $("#set-note").textContent = data.cached === data.count
    ? `Precomputed ${data.cached} of ${data.count}. Replaying from cache.`
    : `Precomputed ${data.cached} of ${data.count}. The rest run live.`;
  await Promise.all(st.msgs.map(async (m) => { st.ex[m.id] = await api(`/api/examine/${m.id}`).catch(() => null); }));
  st.gate = (await api("/api/gate/log")).entries;
  subscribeGate();
  renderAll();
}

function decision(m, mode = st.mode) { return st.ex[m.id]?.decisions?.[mode]; }

function billerName(ex) {
  const b = ex?.biller;
  return ({ bescom: "BESCOM", bwssb: "BWSSB", airtel: "Airtel", lic: "LIC", tataplay: "Tata Play", act: "ACT Fibernet", rwa: "RWA", icici_cc: "ICICI" })[b] || "";
}

function badge(m) {
  const d = decision(m);
  if (!d) return `<div class="badge b-wait"><i class="dot"></i>Checking…</div>`;
  const amt = m.amount ? rs(m.amount) : "";
  if (d.action === "pay") {
    if (m.label === "scam") return `<div class="badge b-scam"><i class="dot"></i>Paid ${amt} — scam</div>`;
    const to = billerName(st.ex[m.id]);
    return `<div class="badge b-paid"><i class="dot"></i>Paid ${amt}${to ? " to " + esc(to) : ""}</div>`;
  }
  if (d.action === "hold") return `<div class="badge b-held"><i class="dot"></i>Held — asked Rahul</div>`;
  return `<div class="badge b-ign"><i class="dot"></i>No action needed</div>`;
}

function visible() {
  return [...st.msgs.slice(0, st.shown), ...Object.values(st.custom || {})];
}

function renderPhone() {
  const vis = visible();
  $("#msgs").innerHTML = vis.map((m) => `
    <div class="m ${st.sel === m.id ? "sel" : ""}" data-id="${esc(m.id)}">
      <div class="from">${esc(m.sender)}<span>${esc(m.time || "")}</span></div>${esc(m.text)}<br>${badge(m)}</div>`).join("");
  $("#msgs").scrollTop = $("#msgs").scrollHeight;
  const last = vis[vis.length - 1];
  $("#clock").textContent = (last?.time || "6:10").replace(/\s*(AM|PM)/i, "");
}

function renderCounters() {
  let paid = 0, scams = 0, held = 0, jev = 0, llm = 0;
  for (const m of visible()) {
    const ex = st.ex[m.id]; const d = decision(m);
    if (!ex || !d) continue;
    if (d.action === "pay") { paid += m.amount || 0; if (m.label === "scam") scams++; }
    if (d.action === "hold") held++;
    jev += st.mode === "double_take" ? ex.cost.jev_usd : ex.cost.jev_only_usd;
    if (st.mode !== "jev_only") llm += ex.cost.llm_usd;
  }
  $("#c-paid").textContent = rs(paid);
  $("#c-scams").textContent = scams;
  $("#c-scams-box").classList.toggle("bad", scams > 0);
  $("#c-held").textContent = held;
  $("#c-jev").textContent = usd(jev, 4);
  $("#c-llm").textContent = usd(llm, 2);
  document.querySelectorAll("#modes button").forEach((b) => {
    b.classList.toggle("on", b.dataset.mode === st.mode);
    b.classList.toggle("dt", b.dataset.mode === "double_take");
  });
}

function cell(c) {
  let cls, txt;
  if (c.kind === "action") { cls = { pay: "cP", hold: "cH", ignore: "cI" }[c.value]; txt = `${ACT[c.value]} ${c.p.toFixed(2).replace(/^0/, "")}`; }
  else { cls = c.value === "legit" ? "cY" : "cN"; txt = c.value === "legit" ? "Legit" : "Scam"; }
  const title = c.kind === "action" ? `P(pay)=${c.p_pay.toFixed(2)}` : `P(yes)=${c.p.toFixed(2)}`;
  return `<div class="c ${cls} ${c.base ? "base" : ""}" title="${title}">${txt}</div>`;
}

function gridHtml(ex, dt) {
  let h = `<div class="grid ${dt ? "" : "muted"}"><div></div><div class="gh" style="grid-column:span 5">What should it do?</div><div></div><div class="gh" style="grid-column:span 2">Is it a scam?</div><div></div><div class="gh" style="grid-column:span 2">Is it genuine?</div>`;
  for (const row of ex.grid) {
    const a = row.filter((c) => c.kind === "action"), s = row.filter((c) => c.kind === "scam"), g = row.filter((c) => c.kind === "genuine");
    h += `<div class="gl" title="${esc(ex.rewrites[row[0].rewrite])}">${esc(row[0].name)}</div>` + a.map(cell).join("") + "<div></div>" + s.map(cell).join("") + "<div></div>" + g.map(cell).join("");
  }
  return h + "</div>";
}

function renderCx() {
  const m = [...st.msgs, ...Object.values(st.custom || {})].find((x) => x.id === st.sel);
  const ex = m && st.ex[m.id];
  if (!m) return `<div class="empty">Press Play, or pick a message on the phone.</div>`;
  if (!ex) return `<div class="empty">Cross-examining ${esc(m.sender)}…</div>`;
  const dt = st.mode === "double_take";
  const d = ex.decisions[st.mode];
  const base = ex.base;
  const op = ex.second_opinion;
  const sub = dt ? `Double Take mode: ${ex.reasks + 1} answers checked before any money moves.`
    : st.mode === "jev_only" ? `Jev only mode: only the ringed answer is used. The other ${ex.reasks} were not consulted.`
    : `Jev + LLM mode: the ringed answer plus the second opinion. The other ${ex.reasks} were not consulted.`;
  const baseCls = base.action === "pay" ? "p-ok" : base.action === "hold" ? "p-warn" : "p-mute";
  const baseTxt = { pay: "Pay now", hold: "Hold", ignore: "No action" }[base.action];
  let opCard = `<div class="card"><small>Second opinion</small><b>Unavailable</b></div>`;
  if (op) {
    const vt = { legitimate: "Legitimate", scam: "Scam", not_a_bill: "Not a bill" }[op.verdict];
    const pill = op.agrees_pay ? `<span class="pill p-ok">agrees: pay</span>` : op.verdict === "scam" ? `<span class="pill p-bad">says: ${op.action}</span>` : `<span class="pill p-mute">says: ${op.action}</span>`;
    opCard = `<div class="card" style="${st.mode === "jev_only" ? "opacity:.45" : ""}"><small>Second opinion, ${esc(op.model)}</small><b>${vt}</b>${pill}<div class="note" style="margin-top:6px">“${esc(op.reason)}”</div></div>`;
  }
  let h = `<div class="cx"><h2>${esc(m.sender)}, ${esc(m.time || "")}</h2><div class="sub">${sub}</div>
    <div class="row"><div class="card"><small>Jev base answer</small><b>${baseTxt}</b><span class="pill ${baseCls}">confidence ${base.confidence.toFixed(2)}</span></div>${opCard}</div>
    ${gridHtml(ex, dt)}`;
  const paidScam = d.action === "pay" && m.label === "scam";
  if (dt) {
    const w = Math.min(100, ex.brittleness * 100);
    h += `<div class="meter"><i style="width:${w}%"></i><span class="tau" style="left:${ex.tau * 100}%"></span></div>
      <div class="mlab"><span>${ex.disagree} of ${ex.reasks} disagree with paying</span><span>brittleness ${ex.brittleness.toFixed(2)}, hold above ${ex.tau.toFixed(2)}</span></div>
      <div class="flags">${ex.flags.map((f) => `<span class="flag ${f.severity}" title="${esc(f.evidence)}">${esc(f.label)}</span>`).join("") || `<span class="note">No red flags.</span>`}</div>
      <div style="display:flex;gap:16px;align-items:flex-start"><div style="flex:1">
        <div class="reasons ${d.action === "pay" ? (paidScam ? "bad" : "ok") : ""}">${reasonHtml(d.reason)}</div>
        <div class="cost">Cost for this message: Jev ${usd(ex.cost.jev_usd, 5)} (${ex.cost.jev_calls} calls, ${ex.cost.jev_ms} ms), second opinion ${usd(ex.cost.llm_usd, 4)} (${(ex.cost.llm_ms / 1000).toFixed(1)} s)</div>
        ${ex.errors?.length ? `<div class="note err">${esc(ex.errors.join("; "))}</div>` : ""}
      </div>${ex.alert ? alertHtml(ex.alert) : ""}</div>`;
  } else {
    let extra = "";
    const dtd = ex.decisions.double_take;
    if (paidScam && dtd.action !== "pay") extra = ` Double Take would have held it (brittleness ${ex.brittleness.toFixed(2)}).`;
    h += `<div class="reasons ${paidScam ? "bad" : d.action === "pay" ? "ok" : ""}" style="margin-top:16px">${reasonHtml(d.reason)}${esc(extra)}</div>
      <div class="cost">Cost for this message: Jev ${usd(ex.cost.jev_only_usd, 5)}${st.mode === "jev_llm" ? `, second opinion ${usd(ex.cost.llm_usd, 4)}` : ""}</div>`;
  }
  return h + "</div>";
}

function reasonHtml(r) {
  const i = r.indexOf(". ");
  return i > 0 && i < 30 ? `<b>${esc(r.slice(0, i + 1))}</b> ${esc(r.slice(i + 2))}` : esc(r);
}

function alertHtml(a) {
  return `<div class="alert"><h3>${esc(a.title)}</h3><div class="who">${esc(a.who)}</div><div class="why">${esc(a.why)}</div>
    <div class="acts"><button class="a1" data-ack="block">${esc(a.actions[0])}</button><button class="a2" data-ack="pay">${esc(a.actions[1])}</button></div></div>`;
}

function renderLog() {
  const rows = st.gate.map((e) => `<div class="l"><span class="t">${esc(e.ts)}</span><span>${esc(e.tool)} ${esc(e.bill_id)} ${esc(e.payee || "")} ${e.amount ? rs(e.amount) : ""}</span>
    <span class="${e.decision === "allow" ? "ok" : "no"}">${e.decision.toUpperCase()}</span><span>${esc(e.reason)}</span></div>`).join("");
  const ag = st.agent;
  return `<div class="cx"><h2>Live run: Codex agent under Failproof</h2><div class="sub">Policy double-take-gate on PreToolUse. Every pay_bill call asks POST /api/gate first.</div></div>
    <div class="log">${rows || `<div class="note">No gate decisions yet. Press “Run Codex under Failproof”.</div>`}</div>
    ${ag?.final ? `<div class="agent"><small>${esc(ag.agent || "Agent")}, final message · ${esc(ag.runner || "")}</small>${esc(ag.final)}</div>`
      : st.agentRunning ? `<div class="agent"><small>Agent</small>Working through the inbox…</div>` : ""}`;
}

async function renderLedger() {
  const led = await api("/api/ledger");
  const tot = MODES.map((k) => { const v = led.modes[k]; return `<div class="card ${k === st.mode ? "cur" : ""}"><small>${MODE_NAME[k]}</small>
    <b>${rs(v.paid)}</b> paid<div class="note" style="margin-top:4px">${v.scams_paid} scams paid (${rs(v.scam_amount)}), ${v.held} held, cost ${usd(v.jev_usd + v.llm_usd, 4)}</div></div>`; }).join("");
  const rows = led.modes[st.mode].rows.map((r) => `<tr><td>${esc(r.id)}</td><td style="font-family:ui-monospace,monospace">${esc(r.sender)}</td><td>${esc(r.label)}</td>
    <td class="${r.action === "pay" ? (r.label === "scam" ? "no" : "ok") : ""}">${esc(r.action)}</td><td>${r.amount ? rs(r.amount) : ""}</td></tr>`).join("");
  return `<div class="cx"><h2>Ledger, whole message set</h2><div class="sub">What each mode would have done with all ${led.messages} messages.</div></div>
    <div class="tot">${tot}</div><table class="led"><tr><th>ID</th><th>Sender</th><th>Truth</th><th>${MODE_NAME[st.mode]}</th><th>Amount</th></tr>${rows}</table>`;
}

async function renderPanel() {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === st.tab));
  const p = $("#panel");
  if (st.tab === "cx") p.innerHTML = renderCx();
  else if (st.tab === "log") p.innerHTML = renderLog();
  else p.innerHTML = await renderLedger().catch((e) => `<div class="empty err">${esc(e.message)}</div>`);
}

function renderAll() { renderPhone(); renderCounters(); renderPanel(); }

function step() {
  if (st.shown >= st.msgs.length) { pause(); return; }
  st.shown++;
  st.sel = st.msgs[st.shown - 1].id;
  renderAll();
  st.timer = setTimeout(step, 1700 / st.speed);
}
function play() { if (st.shown >= st.msgs.length) st.shown = 0; st.playing = true; $("#play").textContent = "Pause"; clearTimeout(st.timer); step(); }
function pause() { st.playing = false; $("#play").textContent = "Play"; clearTimeout(st.timer); }
function replay() { pause(); st.shown = 0; st.sel = null; st.custom = {}; renderAll(); play(); }

function hero() {
  // The most convincing scam that Jev alone paid and Double Take held, from the real cached runs.
  const c = st.msgs.filter((m) => m.label === "scam" && decision(m, "jev_only")?.action === "pay" && decision(m, "double_take")?.action !== "pay")
    .sort((a, b) => st.ex[b.id].base.confidence - st.ex[a.id].base.confidence);
  return c[0] || st.msgs.find((m) => m.id === "S01");
}
function openHero() {
  const h = hero(); if (!h) return;
  pause();
  const i = st.msgs.indexOf(h);
  if (i >= st.shown) st.shown = i + 1;
  st.sel = h.id; st.tab = "cx"; renderAll();
}

function subscribeGate() {
  const es = new EventSource("/api/gate/stream");
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "reset") { st.gate = []; st.agent = null; } else st.gate.push(e);
    if (st.tab === "log") renderPanel();
  };
}

// events
$("#modes").addEventListener("click", (e) => { const m = e.target.dataset.mode; if (m) { st.mode = m; renderAll(); } });
$("#tabs").addEventListener("click", (e) => { const t = e.target.dataset.tab; if (t) { st.tab = t; renderPanel(); } });
$("#speed").addEventListener("click", (e) => {
  const s = e.target.dataset.s; if (!s) return; st.speed = +s;
  document.querySelectorAll("#speed button").forEach((b) => b.classList.toggle("on", b === e.target));
});
$("#play").addEventListener("click", () => (st.playing ? pause() : play()));
$("#replay").addEventListener("click", replay);
$("#msgs").addEventListener("click", (e) => { const el = e.target.closest(".m"); if (el) { st.sel = el.dataset.id; st.tab = "cx"; renderAll(); } });
$("#panel").addEventListener("click", (e) => {
  const a = e.target.dataset.ack; if (!a) return;
  e.target.closest(".alert").querySelector(".why").textContent = a === "block" ? "Blocked and reported. Rahul was told." : "Marked genuine by Rahul. The assistant will pay it.";
});
$("#send").addEventListener("submit", async (e) => {
  e.preventDefault();
  const sender = $("#send-sender").value.trim(), text = $("#send-text").value.trim();
  if (!sender || !text) return;
  pause();
  const t = new Date().toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const tmp = { id: "pending", sender, text, time: t, label: null };
  st.custom = { ...(st.custom || {}), pending: tmp }; st.sel = "pending"; st.tab = "cx"; renderAll();
  $("#send-btn").disabled = true; $("#send-note").textContent = "Asking Jev 36 ways and the second opinion…";
  try {
    const ex = await api("/api/examine", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ sender, text, time: t }) });
    delete st.custom.pending;
    const m = { ...ex.message, time: t };
    const d = ex.decisions.double_take;
    st.custom[m.id] = m; st.ex[m.id] = ex; st.sel = m.id;
    $("#send-note").textContent = `${ex.from_cache ? "From cache" : `Done in ${(ex.cost.wall_ms / 1000).toFixed(1)} s`}. Double Take: ${d.action}.`;
    $("#send-text").value = "";
  } catch (err) {
    delete st.custom.pending; $("#send-note").innerHTML = `<span class="err">${esc(err.message)}</span>`;
  }
  $("#send-btn").disabled = false; renderAll();
});
$("#run-agent").addEventListener("click", async () => {
  st.tab = "log"; st.agent = null; st.agentRunning = true; renderPanel();
  $("#run-agent").disabled = true; $("#run-agent").classList.add("pri"); $("#run-agent").textContent = "Codex run in progress…";
  try {
    st.agent = await api("/api/agent/run", { method: "POST" });
    $("#agent-note").textContent = st.agent.runner ? `Runner: ${st.agent.runner}` : "";
  } catch (err) { $("#agent-note").innerHTML = `<span class="err">${esc(err.message)}</span>`; }
  st.agentRunning = false;
  $("#run-agent").disabled = false; $("#run-agent").classList.remove("pri"); $("#run-agent").textContent = "Run Codex under Failproof";
  renderPanel();
});
document.addEventListener("keydown", (e) => {
  if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName)) return;
  if (e.code === "Space") { e.preventDefault(); st.playing ? pause() : play(); }
  else if (e.key === "1" || e.key === "2" || e.key === "3") { st.mode = MODES[+e.key - 1]; renderAll(); }
  else if (e.key.toLowerCase() === "h") openHero();
});

st.custom = {};
load().catch((e) => { $("#panel").innerHTML = `<div class="empty err">Could not load: ${esc(e.message)}</div>`; });
