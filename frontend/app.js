// Research Desk frontend. All model output and document text is rendered with
// textContent (never innerHTML) - PDF text is untrusted evidence.

const $ = (id) => document.getElementById(id);
const state = { cid: null, answers: new Map(), meta: null, busy: false, adminTimer: null };

const ICON = {
  check: '<path d="M4 10.5l4 4 8-9"/>',
  spark: '<path d="M10 3v4M10 13v4M3 10h4M13 10h4M5.5 5.5l2 2M12.5 12.5l2 2M14.5 5.5l-2 2M7.5 12.5l-2 2"/>',
  globe: '<circle cx="10" cy="10" r="7"/><path d="M3 10h14M10 3c2.5 2.5 2.5 11.5 0 14M10 3c-2.5 2.5-2.5 11.5 0 14"/>',
  shield: '<path d="M10 2.5l6 2.5v5c0 3.5-2.6 6.2-6 7.5-3.4-1.3-6-4-6-7.5V5z"/>',
  alert: '<path d="M10 3l8 14H2z"/><path d="M10 8v4M10 14.5v.01"/>',
  copy: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M13 7V4.5A1.5 1.5 0 0011.5 3h-7A1.5 1.5 0 003 4.5v7A1.5 1.5 0 004.5 13H7"/>',
  doc: '<path d="M5 2.5h7l3 3v12H5z"/><path d="M12 2.5v3h3M7.5 10h5M7.5 13h5"/>',
  ext: '<path d="M11 3h6v6M17 3l-8 8M14 12v4H4V6h4"/>',
  trash: '<path d="M4 6h12M8 6V4h4v2M6 6l1 11h6l1-11"/>',
  q: '<path d="M7.5 7.5a2.5 2.5 0 114 2c-.9.6-1.5 1.1-1.5 2.2M10 14.5v.01"/><circle cx="10" cy="10" r="7.5"/>',
};

function svg(name) {
  const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  s.setAttribute("viewBox", "0 0 20 20");
  s.setAttribute("aria-hidden", "true");
  s.innerHTML = ICON[name]; // static, trusted markup only
  return s;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 2200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (res.status === 401 && path !== "/api/login") { showLogin(); throw new Error("login required"); }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
    throw new Error(detail);
  }
  return res.json();
}

// ------------------------------------------------------------------ meta / freshness
async function loadMeta() {
  try {
    state.meta = await api("/api/meta");
  } catch (e) {
    state.meta = null;
  }
  renderFreshness();
}

function renderFreshness() {
  const f = $("freshness");
  f.replaceChildren();
  const m = state.meta;
  const pill = $("modePill");
  if (!m) {
    f.append(el("span", { class: "expanded", text: "Research services unavailable" }));
    pill.textContent = "Offline";
    pill.className = "mode-pill warn";
    return;
  }
  const c = m.corpus;
  if (!c || !c.window || !c.window.start) {
    f.append(el("span", { class: "expanded", text: m.corpus_error ? "Research service unavailable" : "Knowledge base not built yet — run ingestion from Corpus status" }));
  } else {
    f.append(
      el("span", {}, "Research published ", el("b", { text: c.published_label || "—" })),
      el("span", { class: "sep", text: "·" }),
      el("span", {}, "Corpus window ", el("b", { text: c.window.label })),
      el("span", { class: "sep", text: "·" }),
      el("span", {}, "Refreshed ", el("b", { text: c.refreshed_label || "—" })),
    );
    if (c.window.expanded) f.append(el("span", { class: "expanded", text: `Expanded window (${c.window.days} days)` }));
  }
  const model = m.model || {};
  pill.textContent = model.available ? `Model-assisted · ${model.model}` : "Extractive mode";
  pill.className = "mode-pill " + (model.available ? "ok" : "warn");
  pill.title = model.message || "";
  $("sidebarFoot").textContent = model.available
    ? "Model-assisted synthesis is enabled. Every sentence is validated against cited OCBC evidence."
    : "No model credential configured: answers quote OCBC research verbatim. Set ANTHROPIC_API_KEY to enable synthesis.";
}

// ------------------------------------------------------------------ history
async function loadHistory() {
  const ul = $("history");
  let items = [];
  try { items = await api("/api/conversations"); } catch (_) { /* offline */ }
  ul.replaceChildren();
  if (!items.length) {
    ul.append(el("li", {}, el("span", { class: "empty", text: "No conversations yet" })));
    return;
  }
  for (const c of items) {
    const li = el("li", { class: c.id === state.cid ? "active" : "" },
      el("button", { class: "open", type: "button", title: c.title, text: c.title, onclick: () => openConversation(c.id) }),
      el("button", { class: "del", type: "button", "aria-label": `Delete conversation ${c.title}`, onclick: async (ev) => {
        ev.stopPropagation();
        await api(`/api/conversations/${c.id}`, { method: "DELETE" });
        if (state.cid === c.id) newChat();
        loadHistory();
      } }, svg("trash")));
    ul.append(li);
  }
}

async function openConversation(id) {
  closeNav();
  route("chat");
  const conv = await api(`/api/conversations/${id}`);
  state.cid = id;
  const thread = $("thread");
  thread.replaceChildren();
  for (const m of conv.messages) {
    if (m.role === "user") thread.append(userBubble(m.content));
    else if (m.answer) thread.append(renderAnswer(m.answer));
  }
  thread.scrollTop = thread.scrollHeight;
  loadHistory();
}

function newChat() {
  state.cid = null;
  closeNav();
  route("chat");
  renderEmpty();
  loadHistory();
  $("prompt").focus();
}

// ------------------------------------------------------------------ empty state
function renderEmpty() {
  const thread = $("thread");
  thread.replaceChildren();
  const sugg = (state.meta && state.meta.suggestions) || [
    "What does the latest available research say about USD/SGD through 2027?",
    "Summarize OCBC's published view on SGD interest rates.",
    "What are the main risks identified in the latest credit research?",
  ];
  thread.append(el("div", { class: "hero" },
    el("div", { class: "kicker", text: "OCBC Research Assistant" }),
    el("h1", { text: "Answer client questions from OCBC research — with every number traceable." }),
    el("p", { text: "Ask for forecasts, published rationale or risks. Specialist agents search the ingested OCBC research PDFs; every value and statement is cited to a document page and validated before you see it." }),
    el("div", { class: "suggestions" }, sugg.map((s) => el("button", { class: "suggestion", type: "button", onclick: () => ask(s) }, svg("spark"), el("span", { text: s })))),
    el("div", { class: "hero-note", text: "Suggested questions are examples only — they are not claims that the current corpus contains those answers." }),
  ));
}

function userBubble(text) {
  return el("div", { class: "msg-user" }, el("div", { class: "bubble", text }));
}

// ------------------------------------------------------------------ ask / stream
function progressCard() {
  const list = el("ol");
  const card = el("div", { class: "progress", role: "status" }, list);
  let last = null;
  return {
    node: card,
    step(text) {
      if (last) { last.className = "done"; last.firstChild.replaceChildren(svg("check")); }
      last = el("li", { class: "active" }, el("span", { class: "dot" }), el("span", { text }));
      list.append(last);
    },
    done() { card.remove(); },
  };
}

async function ask(question) {
  question = (question || "").trim();
  if (!question || state.busy) return;
  route("chat");
  state.busy = true;
  $("send").disabled = true;
  const thread = $("thread");
  if (thread.querySelector(".hero")) thread.replaceChildren();
  thread.append(userBubble(question));
  const prog = progressCard();
  prog.step("Sending request");
  thread.append(prog.node);
  thread.scrollTop = thread.scrollHeight;
  $("prompt").value = "";
  autosize();
  try {
    const res = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: question, conversation_id: state.cid }) });
    if (res.status === 401) { prog.done(); showLogin(); return; }
    if (!res.ok || !res.body) {
      let detail = `HTTP ${res.status}`;
      try { detail = (await res.json()).detail || detail; } catch (_) { /* ignore */ }
      throw new Error(detail);
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    let answered = false;
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const chunk = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        if (!chunk.startsWith("data:")) continue;
        const evt = JSON.parse(chunk.slice(5));
        if (evt.type === "conversation") state.cid = evt.conversation_id;
        else if (evt.type === "status") { prog.step(evt.text); thread.scrollTop = thread.scrollHeight; }
        else if (evt.type === "answer") {
          prog.done();
          answered = true;
          thread.append(renderAnswer(evt.answer));
        }
      }
    }
    if (!answered) throw new Error("connection closed before an answer was returned");
  } catch (e) {
    prog.done();
    thread.append(errorCard(`The request could not be completed (${e.message}). No answer was generated — please retry.`));
  } finally {
    state.busy = false;
    $("send").disabled = false;
    thread.scrollTop = thread.scrollHeight;
    loadHistory();
  }
}

function errorCard(msg) {
  return el("div", { class: "answer" }, el("div", { class: "answer-body" },
    el("div", { class: "notice error" }, svg("alert"), el("div", { text: msg }))));
}

// ------------------------------------------------------------------ answer rendering
const STATUS = {
  complete: ["Complete", "ok"], partial: ["Partial coverage", "warn"], no_evidence: ["No verified evidence", "bad"],
  not_covered: ["Not covered by the research", "bad"],
  clarify: ["Needs clarification", "info"], info: ["Info", "info"], error: ["Error", "bad"], declined: ["Declined", "warn"],
};
const LIMIT_LABEL = {
  horizon_not_covered: ["Horizon not covered", "warn"], no_relevant_information: ["No relevant information", "warn"],
  subject_not_covered: ["Not covered", "warn"],
  document_inaccessible: ["Document inaccessible", "bad"], extraction_failed: ["Extraction failed", "bad"],
  conflicting_sources: ["Conflicting sources", "warn"], missing_coverage: ["Not published", "warn"],
  note: ["Note", "info"], mixed_dates: ["Mixed dates", "info"], validation: ["Validation", "warn"], model: ["Model", "info"],
  error: ["Error", "bad"], horizon_passed: ["Horizon passed", "warn"], limitation: ["Limitation", ""],
};

function citeChips(answer, nums) {
  return (nums || []).map((n) => el("button", { class: "cite", type: "button", title: `Open source ${n}`,
    "aria-label": `Source ${n}`, onclick: () => openSource(answer, n), text: String(n) }));
}

function freshBadge(fr) {
  if (!fr) return null;
  const cls = "badge fresh-" + fr.label.split(" ")[0];
  const age = fr.age_days === null || fr.age_days === undefined ? "" : ` · ${fr.age_days}d old`;
  return el("span", { class: cls, title: fr.rule, text: fr.label + age });
}

function claimList(answer, items, cls = "") {
  const sourceBy = new Map(answer.sources.map((s) => [s.n, s]));
  return el("ul", { class: "claims" }, items.map((c) => {
    const first = sourceBy.get((c.citations || [])[0]);
    return el("li", { class: cls },
      el("div", { class: "q" }, c.mode === "verbatim" ? `“${c.text}”` : c.text, " ", citeChips(answer, c.citations)),
      first ? el("div", { class: "meta" },
        el("span", { text: `${first.title} · ${first.publication_label} · p.${first.pdf_page}` }),
        freshBadge(first.freshness), c.specialist ? el("span", { class: "badge", text: c.specialist }) : null,
        c.mode === "summary" ? el("span", { class: "badge info", text: "Summary (validated)" }) : null) : null);
  }));
}

// Client-facing layout: executive summary, ONE forecast table (horizons across,
// one instrument per row), the key implication, then supporting research,
// sources and the audit trail collapsed underneath.
// Gaps in what was asked lead the summary, so a missing forecast is never buried.
const LEAD_LIMITS = new Set(["horizon_not_covered", "subject_not_covered"]);
// Gaps in what was asked lead the summary; l.lead marks a per-answer one (no write-up on an instrument asked about).
const leads = (l) => LEAD_LIMITS.has(l.type) || l.lead === true;
// Executive summary paragraphs: view and path together, then why, risks, conclusion.
const PART_PARA = { view: 0, path: 0, why: 1, risks: 2, conclusion: 3 };
function summaryParagraphs(direct) {
  const paras = [];
  let last = null;
  for (const c of direct) {
    const p = PART_PARA[c.part] ?? (last ?? 0);
    if (p !== last || !paras.length) paras.push([]);
    paras[paras.length - 1].push(c);
    last = p;
  }
  return paras;
}
const MATERIAL_LIMITS = new Set(["horizon_not_covered", "subject_not_covered", "no_relevant_information", "document_inaccessible",
  "extraction_failed", "conflicting_sources", "missing_coverage", "error", "horizon_passed"]);

function tableGroups(rows) {
  // One table per horizon kind; columns keep the published order of horizons.
  const groups = [];
  for (const kind of ["absolute", "relative"]) {
    const list = rows.filter((r) => (r.horizon_kind === "absolute") === (kind === "absolute"));
    if (!list.length) continue;
    const horizons = [...new Set(list.map((r) => r.horizon))];
    const byInst = new Map();
    for (const r of list) {
      if (!byInst.has(r.instrument)) byInst.set(r.instrument, { instrument: r.instrument, unit: r.unit, cells: new Map(), cites: new Set() });
      const g = byInst.get(r.instrument);
      g.cells.set(r.horizon, r);
      r.citations.forEach((c) => g.cites.add(c));
    }
    groups.push({ kind, horizons, rows: [...byInst.values()] });
  }
  return groups;
}

function instName(inst, unit) {
  // "Gold $/oz" with unit "$/oz" -> "Gold": the unit is shown once, separately.
  return unit && inst.endsWith(unit) ? inst.slice(0, -unit.length).trim() : inst;
}

function tableTitle(rows) {
  // Name what was asked about; related tenors shown alongside are mentioned, not listed.
  const asked = rows.filter((r) => r.asked !== false);
  const names = [...new Set((asked.length ? asked : rows).map((r) => instName(r.instrument, r.unit)))];
  const units = [...new Set(rows.map((r) => r.unit).filter(Boolean))];
  const list = names.length > 4 ? names.slice(0, 4).join(", ") + " and others"
    : names.length > 1 ? names.slice(0, -1).join(", ") + " and " + names[names.length - 1] : names[0];
  const related = asked.length && asked.length < rows.length ? ", with related tenors" : "";
  return `${list} forecast${related}${units.length === 1 ? ` (${units[0]})` : ""}`;
}

function asOfLines(rows) {
  // "Latest Forecast Update: 30 October 2026 · FX Weekly: Firm, Not One-Way, published 2 Nov 2026"
  const seen = new Map();
  for (const r of rows) {
    const key = `${r.data_date || ""}|${r.doc_title || ""}|${r.publication_label}`;
    if (!seen.has(key)) seen.set(key, [r.data_date, r.doc_title ? `${r.doc_title}, published ${r.publication_label}` : `Published ${r.publication_label}`].filter(Boolean).join(" · "));
  }
  return [...seen.values()];
}

function renderTable(answer) {
  const tables = tableGroups(answer.table).map((g) => {
    const head = el("tr", {}, el("th", { text: "" }), g.horizons.map((h) => el("th", { class: "num", text: h })), el("th", { text: "" }));
    const body = el("tbody", {}, g.rows.map((r) => el("tr", {},
      el("td", {}, instName(r.instrument, r.unit), r.unit && !tableTitle(answer.table).endsWith(`(${r.unit})`)
        ? el("span", { class: "muted", text: ` (${r.unit})` }) : null),
      g.horizons.map((h) => {
        const c = r.cells.get(h);
        return el("td", { class: "num", title: c && c.horizon_passed ? "This horizon has passed" : "" },
          c ? c.value : "—", c && c.horizon_passed ? el("sup", { class: "passed", text: "passed" }) : null);
      }),
      el("td", { class: "src" }, citeChips(answer, [...r.cites])))));
    return el("div", { class: "table-wrap" }, el("table", { class: "fc" },
      g.kind === "relative" && answer.table.some((r) => r.horizon_kind === "absolute")
        ? el("caption", { text: "Relative horizons (as published)" }) : null,
      el("thead", {}, head), body));
  });
  const notes = answer.table_notes.filter((n) => n.mode === "verbatim");
  return el("div", {},
    el("div", { class: "table-title", text: tableTitle(answer.table) }),
    tables,
    el("div", { class: "table-meta" },
      asOfLines(answer.table).map((t) => el("div", { class: "asof", text: t })),
      notes.map((n) => el("div", { class: "note" }, el("span", { text: n.text }), citeChips(answer, n.citations)))));
}

function renderAnswer(a) {
  if (a.answer_id) state.answers.set(a.answer_id, a);
  const [statusText, statusCls] = STATUS[a.status] || [a.status, ""];
  const head = el("div", { class: "answer-head" },
    a.status !== "complete" ? el("span", { class: `badge ${statusCls}`, text: statusText }) : null,
    el("span", { class: "spacer" }),
    el("span", { class: "badge", text: `Generated ${a.generated_label}` }));
  const body = el("div", { class: "answer-body" });
  for (const n of a.notices || []) {
    body.append(el("div", { class: `notice ${n.kind}` }, svg(n.kind === "web" ? "globe" : "shield"), el("div", { text: n.text })));
  }
  if (a.message) body.append(el("p", { class: "empty-answer", text: a.message }));
  const gaps = (a.limitations || []).filter(leads).map((l) => l.text);
  if (a.direct && a.direct.length) {
    body.append(el("div", { class: "section direct" }, el("h3", { text: "Executive summary" }),
      summaryParagraphs(a.direct).map((para, i) => el("p", { class: "lead" }, i === 0 ? gaps.map((g) => g + " ") : null,
        para.flatMap((c) => [c.text, " ", ...citeChips(a, c.citations), " "])))));
  } else if (a.no_evidence_message) {
    body.append(el("div", { class: "section direct" }, el("h3", { text: "Executive summary" }), el("p", { class: "lead", text: a.no_evidence_message })));
  }
  if (a.table && a.table.length) body.append(el("div", { class: "section" }, renderTable(a)));
  const implication = (a.table_notes || []).filter((n) => n.mode !== "verbatim");
  if (implication.length) {
    body.append(el("div", { class: "section direct" }, implication.map((c) => el("p", {}, c.text, " ", citeChips(a, c.citations)))));
  }
  if (a.conflicts && a.conflicts.length) {
    body.append(el("div", { class: "section" }, el("h3", { text: "Differing views in the research" }),
      el("ul", { class: "limits" }, a.conflicts.map((c) => el("li", {},
        el("span", { class: `badge ${c.resolution === "unresolved" ? "bad" : "info"}`, text: c.resolution === "unresolved" ? "Unresolved" : "Revision" }),
        el("span", { text: c.text }))))));
  }
  const material = (a.limitations || []).filter((l) => MATERIAL_LIMITS.has(l.type) && !(a.direct.length && leads(l)));
  const minor = (a.limitations || []).filter((l) => !MATERIAL_LIMITS.has(l.type));
  if (material.length) {
    body.append(el("div", { class: "section please-note" }, el("h3", { text: "Please note" }),
      el("ul", { class: "limits" }, material.map((l) => el("li", { text: l.text })))));
  }
  if (a.suggestions && a.suggestions.length) {
    body.append(el("div", { class: "suggestions" }, a.suggestions.map((s) => el("button", { class: "suggestion", type: "button", onclick: () => ask(s) }, svg("spark"), el("span", { text: s })))));
  }
  const support = [...(a.rationale || []), ...(a.risks || []), ...(a.scenarios || [])];
  if (support.length) {
    body.append(el("details", { class: "more" }, el("summary", {}, "Supporting research", el("span", { class: "count", text: ` · ${support.length} excerpts` })),
      a.rationale.length ? claimList(a, a.rationale) : null,
      a.risks.length ? el("div", {}, el("h4", { text: "Risks" }), claimList(a, a.risks, "risk")) : null,
      (a.scenarios || []).length ? el("div", {}, el("h4", { text: "Scenarios" }), claimList(a, a.scenarios)) : null));
  }
  if (a.sources && a.sources.length) {
    body.append(el("details", { class: "more" }, el("summary", {}, "Sources", el("span", { class: "count", text: ` · ${a.sources.length}` })),
      el("ol", { class: "sources" }, a.sources.map((s) => el("li", { tabindex: "0", role: "button", onclick: () => openSource(a, s.n),
        onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSource(a, s.n); } } },
        el("span", { class: "n", text: String(s.n) }),
        el("div", {},
          el("div", { class: "t", text: s.title }),
          el("div", { class: "m" }, el("span", { text: `Published ${s.publication_label}` }),
            el("span", { text: `PDF p.${s.pdf_page}${s.printed_page && s.printed_page !== String(s.pdf_page) ? ` (printed ${s.printed_page})` : ""}` }),
            s.data_date ? el("span", { text: s.data_date }) : null,
            s.ocr ? el("span", { class: "badge warn", text: "OCR" }) : null),
          el("div", { class: "x", text: s.excerpt })),
        freshBadge(s.freshness))))));
  }
  const fr = a.freshness || {};
  if (a.plan || (a.sources && a.sources.length)) {
    body.append(el("details", { class: "audit" }, el("summary", { text: "How this answer was produced" }),
      a.sources && a.sources.length ? el("div", { class: "dates-strip" },
        el("span", {}, "Sources published ", el("b", { text: fr.research_published || "—" })),
        el("span", {}, "Corpus window ", el("b", { text: fr.corpus_window || "—" })),
        el("span", {}, "Corpus refreshed ", el("b", { text: fr.corpus_refreshed || "—" })),
        el("span", {}, "Answer generated ", el("b", { text: a.generated_label })),
        fr.expanded ? el("span", { class: "badge warn", text: "Expanded date range" }) : null) : null,
      a.mode && a.mode !== "none" ? el("div", { text: `Mode: ${a.mode === "model_assisted" ? "model-assisted summary (validated)" : "extractive (summary quotes the research and uses fixed wording around forecast values)"} · specialists: ${(a.specialists || []).join(", ") || "—"}` }) : null,
      a.plan ? el("div", { text: `Lead specialist: ${a.plan.lead || "—"} · consulted: ${a.plan.specialists.join(", ")} · instruments: ${(a.plan.instruments || []).join(", ") || "—"} · horizon: ${a.plan.horizon || "—"} · requested: ${a.plan.info_types.join(", ")}${a.plan.inherited_context ? " · follow-up context inherited" : ""}${(a.plan.search_terms || []).length ? ` · search terms added: ${a.plan.search_terms.join(", ")}` : ""}` }) : null,
      a.validation ? el("div", { text: `Validation checks: ${a.validation.checks.join(", ")}. Removed: ${a.validation.removed}.` }) : null,
      minor.length ? el("ul", { class: "limits" }, minor.map((l) => {
        const [lab, cls] = LIMIT_LABEL[l.type] || [l.type, ""];
        return el("li", {}, el("span", { class: `badge ${cls}`, text: lab }), el("span", { text: (l.specialist ? `${l.specialist}: ` : "") + l.text }));
      })) : null));
  }
  const foot = el("div", { class: "answer-foot" });
  if (a.sources && a.sources.length) {
    foot.append(el("span", { class: "verify" }, svg("check"), `${a.sources.length} citations verified against source pages${a.validation && a.validation.removed ? ` · ${a.validation.removed} unsupported item(s) removed` : ""}`));
    foot.append(el("button", { class: "btn btn-ghost", type: "button", onclick: () => copyText(answerMarkdown(a), "Answer copied") }, svg("copy"), "Copy answer"));
    if (a.table && a.table.length) foot.append(el("button", { class: "btn btn-ghost", type: "button", onclick: () => copyText(tableMarkdown(a), "Table copied") }, svg("copy"), "Copy table"));
  }
  return el("article", { class: "answer" }, head, body, foot.childNodes.length ? foot : null);
}

// ------------------------------------------------------------------ copy
function refs(a, nums) {
  return (nums || []).map((n) => `[${n}]`).join("");
}
function sourceLines(a, only) {
  return a.sources.filter((s) => !only || only.has(s.n)).map((s) =>
    `[${s.n}] ${s.title}, published ${s.publication_label}, p.${s.pdf_page}`);
}
function tableMarkdownRows(a) {
  const lines = [`**${tableTitle(a.table)}**`, ""];
  for (const g of tableGroups(a.table)) {
    lines.push(`| ${g.kind === "relative" ? "Horizon (as published)" : ""} | ${g.horizons.join(" | ")} |`,
      `|---|${g.horizons.map(() => "--:").join("|")}|`);
    for (const r of g.rows) {
      lines.push(`| ${instName(r.instrument, r.unit)}${r.unit && !tableTitle(a.table).endsWith(`(${r.unit})`) ? ` (${r.unit})` : ""} | ${g.horizons.map((h) => {
        const c = r.cells.get(h);
        return c ? c.value + (c.horizon_passed ? " (passed)" : "") : "—";
      }).join(" | ")} |`);
    }
    lines.push("");
  }
  lines.push(...asOfLines(a.table));
  return lines;
}
function citedIn(items) {
  return new Set(items.flatMap((c) => c.citations || []));
}
function tableMarkdown(a) {
  const used = citedIn(a.table);
  return [...tableMarkdownRows(a), "", "Sources:", ...sourceLines(a, used)].join("\n");
}
function answerMarkdown(a) {
  // Client-ready text: summary, table, implication, material notes, sources.
  const out = [];
  for (const n of a.notices || []) out.push(`Note: ${n.text}`, "");
  const gaps = a.direct.length ? a.limitations.filter(leads).map((l) => l.text) : [];
  summaryParagraphs(a.direct).forEach((para, i) =>
    out.push([...(i === 0 ? gaps : []), ...para.map((c) => `${c.text} ${refs(a, c.citations)}`.trim())].join(" "), ""));
  if (!a.direct.length && a.no_evidence_message) out.push(a.no_evidence_message, "");
  const implication = a.table_notes.filter((n) => n.mode !== "verbatim");
  if (a.table.length) out.push(...tableMarkdownRows(a), "");
  if (implication.length) out.push(implication.map((c) => `${c.text} ${refs(a, c.citations)}`).join(" "), "");
  if (a.conflicts.length) a.conflicts.forEach((c) => out.push(`Note: ${c.text}`));
  const notes = a.limitations.filter((l) => MATERIAL_LIMITS.has(l.type) && !gaps.includes(l.text));
  notes.forEach((l) => out.push(`Note: ${l.text}`));
  if (a.conflicts.length || notes.length) out.push("");
  const used = citedIn([...a.direct, ...a.table, ...implication]);
  out.push("Sources:", ...sourceLines(a, used));
  out.push("", "Source: OCBC Group Research. Consolidation of published research; not investment advice.");
  return out.join("\n");
}
async function copyText(text, msg) {
  try { await navigator.clipboard.writeText(text); toast(msg); }
  catch (_) {
    const ta = el("textarea", { style: "position:fixed;opacity:0" });
    ta.value = text; document.body.append(ta); ta.select();
    try { document.execCommand("copy"); toast(msg); } catch (__) { toast("Copy failed"); }
    ta.remove();
  }
}

// ------------------------------------------------------------------ source drawer
async function openSource(answer, n) {
  const s = answer.sources.find((x) => x.n === n);
  if (!s) return;
  const drawer = $("drawer");
  drawer.hidden = false;
  $("scrim").hidden = false;
  $("drawerKicker").textContent = `Source ${n}`;
  $("drawerTitle").textContent = s.title;
  const body = $("drawerBody");
  body.replaceChildren(el("div", { class: "excerpt", text: s.excerpt }));
  let meta = null;
  try { meta = await api(`/api/docs/${encodeURIComponent(s.doc_id)}`); }
  catch (e) { body.append(el("div", { class: "notice error" }, svg("alert"), el("div", { text: `Document details unavailable (${e.message}).` }))); }
  const pdfUrl = `/api/docs/${encodeURIComponent(s.doc_id)}/pdf#page=${s.pdf_page}`;
  // Documents added by hand (not on ocbc.com) carry a "manual:" source instead of a link.
  const online = /^https:\/\//.test(s.url || "");
  const where = online ? s.url : "not published online (added manually)";
  body.append(el("div", { class: "drawer-actions" },
    el("a", { class: "btn btn-primary", href: pdfUrl, target: "_blank", rel: "noopener" }, svg("doc"), `Open PDF at page ${s.pdf_page}`),
    online ? el("a", { class: "btn", href: s.url, target: "_blank", rel: "noopener noreferrer" }, svg("ext"), "Original on ocbc.com") : null,
    el("button", { class: "btn btn-ghost", type: "button", onclick: () => copyText(`${s.title} — published ${s.publication_label}, PDF p.${s.pdf_page} — ${where}\n"${s.excerpt}"`, "Citation copied") }, svg("copy"), "Copy citation")));
  const kv = el("dl", { class: "kv" });
  const add = (k, v) => { if (v !== null && v !== undefined && v !== "") kv.append(el("dt", { text: k }), el("dd", {}, v)); };
  add("Publication date", `${s.publication_label} (${meta ? meta.date_basis : "—"}; confidence ${s.date_confidence})`);
  if (meta) {
    add("Website listing date", meta.listing_date || "—");
    add("Printed date", meta.printed_date || "—");
  }
  add("Data date (stated)", s.data_date);
  add("Document age", freshBadge(s.freshness));
  add("Freshness rule", s.freshness ? s.freshness.rule : null);
  add("Report type", s.report_type);
  add("Page", `PDF page ${s.pdf_page}${s.printed_page ? ` · printed page ${s.printed_page}` : ""}${meta ? ` of ${meta.page_count}` : ""}`);
  add("Section", s.section);
  add("Document ID", s.doc_id);
  if (meta) add("Content hash", meta.sha256.slice(0, 16) + "…");
  add("Source URL", online ? el("a", { href: s.url, target: "_blank", rel: "noopener noreferrer", text: s.url })
    : "Not published on ocbc.com — added manually");
  body.append(kv);
  if (s.ocr) body.append(el("div", { class: "flag", text: "This excerpt was extracted by OCR from an image-only page — verify against the page image." }));
  if (meta && meta.date_flags && meta.date_flags.length) meta.date_flags.forEach((f) => body.append(el("div", { class: "flag", text: f })));
  const img = el("img", { class: "page-img", alt: `Page ${s.pdf_page} of ${s.title} with the cited excerpt highlighted`, loading: "lazy",
    src: `/api/docs/${encodeURIComponent(s.doc_id)}/pages/${s.pdf_page}.png?q=${encodeURIComponent(s.excerpt.slice(0, 3500))}` });
  img.addEventListener("error", () => img.replaceWith(el("div", { class: "notice error" }, svg("alert"), el("div", { text: "Page image could not be rendered." }))));
  body.append(el("div", { class: "section" }, el("h3", { text: "Cited page (excerpt highlighted)" }), img));
  $("drawerClose").focus();
}
function closeDrawer() { $("drawer").hidden = true; $("scrim").hidden = !document.getElementById("app").classList.contains("nav-open"); }

// ------------------------------------------------------------------ admin view
const STATE_LABEL = {
  indexed: ["Indexed", "ok"], unchanged: ["Unchanged", "ok"], duplicate: ["Duplicate", "info"], excluded_date: ["Excluded by date", ""],
  quarantined: ["Quarantined (date)", "warn"], failed_download: ["Download failed", "bad"], inaccessible: ["Inaccessible", "bad"],
  invalid_pdf: ["Invalid PDF", "bad"], parse_failed: ["Parse failed", "bad"], discovered: ["Pending", "info"],
};

async function renderAdmin() {
  const view = $("viewAdmin");
  let s;
  try { s = await api("/api/admin/status"); }
  catch (e) { view.replaceChildren(el("div", { class: "admin" }, errorCard(`Corpus status unavailable (${e.message}).`))); return; }
  const latest = s.latest_run;
  const sum = (latest && latest.summary) || {};
  const counts = s.counts || {};
  const failures = (s.items || []).filter((i) => ["failed_download", "inaccessible", "invalid_pdf", "parse_failed", "quarantined"].includes(i.state));
  const window = s.active_window;
  const complete = sum.complete;
  const running = s.job && s.job.running;
  const head = el("div", { class: "admin-head" },
    el("div", {}, el("h1", { text: "Corpus status" }),
      el("p", { text: window ? `Ingestion window ${window.label} (inclusive, Asia/Singapore) · ${window.days} calendar days${window.expanded ? " · EXPANDED beyond the default" : ""}` : "No successful ingestion yet." })),
    s.public_mode ? el("span", { class: "badge info", text: "Read-only hosted demo" }) :
    el("div", { class: "controls" },
      el("button", { class: "btn btn-primary", type: "button", disabled: running, onclick: async () => {
        try { await api("/api/admin/ingest", { method: "POST", body: "{}" }); toast("Refresh started"); renderAdmin(); } catch (e) { toast(e.message); }
      } }, running ? "Ingestion running…" : `Refresh (${s.default_window_days}-day window)`)));
  const cards = el("div", { class: "cards" },
    card("Last successful ingestion", s.last_successful_run ? fmtTs(s.last_successful_run.finished_at) : "never", latest ? `Run ${latest.run_id}` : ""),
    card("Discovered", sum.discovered ?? "—", `${sum.sections_checked ?? 0} pages / sections checked`),
    card("Downloaded & indexed", (counts.indexed || 0) + (counts.unchanged || 0), counts.unchanged ? `${counts.unchanged} unchanged since last run` : "new this run"),
    card("Excluded by date", counts.excluded_date || 0, "publication date outside window"),
    card("Duplicates", counts.duplicate || 0, "same content hash"),
    card("Failures / quarantined", failures.length, complete ? "coverage complete" : "coverage incomplete — see below"));
  const covRows = Object.entries(s.coverage || {}).map(([k, v]) => {
    const max = Math.max(1, ...Object.values(s.coverage).map((x) => x.documents));
    return el("tr", {}, el("td", { text: k.toUpperCase() }), el("td", { class: "num", text: v.documents }),
      el("td", { class: "num", text: v.chunks }), el("td", { class: "num", text: v.forecast_records }),
      el("td", {}, el("div", { class: "bar" }, el("span", { style: `width:${(100 * v.documents / max).toFixed(0)}%` }))));
  });
  const coverage = el("div", { class: "panel" }, el("h2", { text: "Coverage by specialist collection" }),
    el("table", { class: "list" }, el("thead", {}, el("tr", {}, ["Specialist", "Documents", "Passages", "Forecast cells", ""].map((h) => el("th", { text: h })))), el("tbody", {}, covRows)),
    el("p", { class: "policy", text: s.semantic_retrieval ? "Hybrid retrieval: exact-token BM25 + local semantic embeddings." : "Semantic retrieval unavailable — lexical retrieval only." }));
  const sections = el("div", { class: "panel" }, el("h2", { text: "Pages and sections checked" }),
    el("div", { class: "table-wrap", style: "border:0" }, el("table", { class: "list" },
      el("thead", {}, el("tr", {}, ["Source", "Section", "Status", "Items"].map((h) => el("th", { text: h })))),
      el("tbody", {}, (s.section_checks || []).map((c) => el("tr", {},
        el("td", { text: c.source }), el("td", { text: c.section || c.category || "—" }),
        el("td", {}, el("span", { class: `badge ${c.status === "failed" ? "bad" : c.status === "ok" ? "ok" : ""}`, text: c.status + (c.detail ? ` — ${c.detail}` : "") })),
        el("td", { class: "num", text: c.items })))))));
  const docs = el("div", { class: "panel" }, el("h2", { text: "Documents" }),
    el("div", { class: "table-wrap", style: "border:0" }, el("table", { class: "list" },
      el("thead", {}, el("tr", {}, ["Title", "Published", "Age", "Date basis", "Specialists", "Status"].map((h) => el("th", { text: h })))),
      el("tbody", {}, (s.documents || []).map((d) => el("tr", {},
        el("td", {}, el("div", { text: d.title }), d.date_flags.length ? el("div", { class: "flag", text: d.date_flags.join(" · ") }) : null,
          d.ocr_pages.length ? el("span", { class: "badge warn", text: `OCR pages: ${d.ocr_pages.join(", ")}` }) : null,
          d.dev_fixture ? el("span", { class: "badge bad", text: "DEV FIXTURE" }) : null),
        el("td", { text: d.publication_date || "unknown" }),
        el("td", {}, freshBadge(d.freshness)),
        el("td", { class: "muted", text: `${d.date_basis || "—"} (${d.date_confidence || "—"})` }),
        el("td", { text: d.specialists.map((x) => x.toUpperCase()).join(", ") || "—" }),
        el("td", {}, el("span", { class: `badge ${d.status === "indexed" ? "ok" : d.status === "excluded_date" ? "" : "warn"}`, text: d.status + (d.status_detail ? ` — ${d.status_detail}` : "") }))))))));
  const fails = el("div", { class: "panel" }, el("h2", { text: "Inaccessible, failed and quarantined" }),
    failures.length ? el("ul", { class: "limits" }, failures.map((f) => el("li", {}, el("span", { class: `badge ${(STATE_LABEL[f.state] || ["", "bad"])[1]}`, text: (STATE_LABEL[f.state] || [f.state])[0] }),
      el("span", { text: `${f.title || f.url} — ${f.detail}` })))) : el("p", { class: "policy", text: "None in the latest run." }),
    (s.suspicious_passages || []).length ? el("div", {}, el("h2", { text: "Passages withheld (embedded instructions)", style: "margin-top:14px" }),
      el("ul", { class: "limits" }, s.suspicious_passages.map((p) => el("li", {}, el("span", { class: "badge bad", text: "Withheld" }), el("span", { text: `${p.title} p.${p.pdf_page}: ${p.suspicious_reason}` }))))) : null);
  const excluded = (s.items || []).filter((i) => i.state === "excluded_date");
  const excl = el("details", { class: "panel" }, el("summary", { text: `Excluded by date (${excluded.length})` }),
    el("table", { class: "list" }, el("tbody", {}, excluded.map((i) => el("tr", {}, el("td", { text: i.title || i.url }), el("td", { class: "muted", text: i.detail }))))));
  const pol = s.freshness_policy || { policies: {} };
  const fresh = el("div", { class: "panel" }, el("h2", { text: "Freshness policy" }),
    el("div", { class: "policy" }, el("div", { text: pol._doc || "" }),
      Object.entries(pol.policies).map(([k, v]) => el("div", {}, el("b", { text: `${v.label}: ` }), `Recent ≤ ${v.recent_max_days} days · Older ≤ ${v.older_max_days} days · Stale beyond`))));
  const daysInput = el("input", { type: "number", min: "1", max: "90", value: String(s.default_window_days), "aria-label": "Window length in days" });
  const cronInput = el("input", { type: "text", value: (s.schedule && s.schedule.cron) || "", placeholder: "e.g. 0 8 * * *", "aria-label": "Refresh schedule (cron)" });
  const ops = el("div", { class: "panel" }, el("h2", { text: "Refresh and schedule" }),
    el("div", { class: "controls" },
      el("label", {}, "Scheduled refresh (cron, SGT)", cronInput),
      el("button", { class: "btn", type: "button", onclick: async () => {
        try { await api("/api/admin/schedule", { method: "PUT", body: JSON.stringify({ cron: cronInput.value }) }); toast("Schedule saved"); renderAdmin(); } catch (e) { toast(e.message); }
      } }, "Save schedule"),
      el("span", { class: "policy", text: s.schedule && s.schedule.next_run ? `Next run ${fmtTs(s.schedule.next_run)}` : "Scheduler disabled" })),
    el("div", { class: "controls", style: "margin-top:12px" },
      el("label", {}, "Explicit window (days)", daysInput),
      el("button", { class: "btn", type: "button", disabled: running, onclick: async () => {
        const d = parseInt(daysInput.value, 10);
        if (d !== s.default_window_days && !confirm(`Run ingestion with a ${d}-day window? This differs from the default ${s.default_window_days}-day window and will be shown as an expanded range in every answer.`)) return;
        try { await api("/api/admin/ingest", { method: "POST", body: JSON.stringify({ days: d }) }); toast("Ingestion started"); renderAdmin(); } catch (e) { toast(e.message); }
      } }, "Run with this window")),
    s.job && s.job.log && s.job.log.length ? el("div", { class: "log", style: "margin-top:12px", text: s.job.log.join("\n") }) : null,
    s.job && s.job.error ? el("div", { class: "notice error", style: "margin-top:10px" }, svg("alert"), el("div", { text: s.job.error })) : null);
  view.replaceChildren(el("div", { class: "admin" }, head,
    !complete && latest ? el("div", { class: "notice advice" }, svg("alert"), el("div", { text: "Coverage is not complete: at least one section or document could not be checked. Answers will disclose this." })) : null,
    s.public_mode ? el("div", { class: "notice info" }, svg("shield"), el("div", { text: "This hosted demo serves a fixed corpus built on " + (s.last_successful_run ? fmtTs(s.last_successful_run.finished_at) : "—") + ". Crawling, refresh and scheduling are disabled here; the corpus is rebuilt and re-uploaded by the administrator." })) : null,
    cards, el("div", { class: "grid-2" }, coverage, fresh), s.public_mode ? null : ops, fails, sections, docs, excl));
  clearTimeout(state.adminTimer);
  if (running) state.adminTimer = setTimeout(() => { if (!$("viewAdmin").hidden) renderAdmin(); }, 3000);
  else loadMeta();
}
function card(k, v, sub) { return el("div", { class: "card" }, el("div", { class: "k", text: k }), el("div", { class: "v", text: String(v) }), el("div", { class: "s", text: sub || "" })); }
function fmtTs(iso) {
  try {
    return new Intl.DateTimeFormat("en-SG", { timeZone: "Asia/Singapore", day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(iso)) + " SGT";
  } catch (_) { return iso; }
}

// ------------------------------------------------------------------ routing / chrome
function route(name, push = true) {
  const admin = name === "admin";
  $("viewChat").hidden = admin;
  $("viewAdmin").hidden = !admin;
  $("navChat").classList.toggle("active", !admin);
  $("navAdmin").classList.toggle("active", admin);
  if (push && location.pathname !== (admin ? "/admin" : "/")) history.pushState({}, "", admin ? "/admin" : "/");
  if (admin) renderAdmin();
}
function closeNav() { $("app").classList.remove("nav-open"); $("scrim").hidden = $("drawer").hidden; }
function autosize() { const t = $("prompt"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 220) + "px"; }

$("composer").addEventListener("submit", (e) => { e.preventDefault(); ask($("prompt").value); });
$("prompt").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask($("prompt").value); } });
$("prompt").addEventListener("input", autosize);
$("newChat").addEventListener("click", newChat);
$("navChat").addEventListener("click", (e) => { e.preventDefault(); closeNav(); route("chat"); if (!$("thread").childNodes.length) renderEmpty(); });
$("navAdmin").addEventListener("click", (e) => { e.preventDefault(); closeNav(); route("admin"); });
$("menuBtn").addEventListener("click", () => { $("app").classList.add("nav-open"); $("scrim").hidden = false; });
$("scrim").addEventListener("click", () => { closeNav(); closeDrawer(); });
$("drawerClose").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); closeNav(); } });
window.addEventListener("popstate", () => route(location.pathname === "/admin" ? "admin" : "chat", false));

// ------------------------------------------------------------------ login
function showLogin(message) {
  if (document.getElementById("login")) return;
  const input = el("input", { type: "password", id: "loginPassword", autocomplete: "current-password", required: true,
    "aria-label": "Access password", placeholder: "Access password" });
  const err = el("div", { class: "login-error", role: "alert", text: message || "" });
  const form = el("form", { class: "login-card", onsubmit: async (e) => {
    e.preventDefault();
    err.textContent = "";
    try {
      await api("/api/login", { method: "POST", body: JSON.stringify({ password: input.value }) });
      location.reload();
    } catch (ex) { err.textContent = ex.message === "HTTP 401" ? "Incorrect password." : ex.message; input.select(); }
  } },
    el("span", { class: "brand-mark", "aria-hidden": "true" }),
    el("h1", { text: "Research Desk" }),
    el("p", { text: "OCBC research assistant. Enter the access password you were given." }),
    input, err, el("button", { class: "btn btn-primary btn-block", type: "submit", text: "Sign in" }));
  document.body.append(el("div", { class: "login", id: "login" }, form));
  input.focus();
}

(async function init() {
  try {
    const sess = await api("/api/session");
    state.session = sess;
    if (!sess.authenticated) { showLogin(); return; }
    if (sess.password_required) {
      $("sidebarFoot").after(el("button", { class: "btn btn-ghost signout", type: "button", text: "Sign out", onclick: async () => {
        await api("/api/logout", { method: "POST", body: "{}" }); location.reload(); } }));
    }
  } catch (_) { /* gateway unreachable: meta will show offline */ }
  await loadMeta();
  renderEmpty();
  loadHistory();
  route(location.pathname === "/admin" ? "admin" : "chat", false);
})();
