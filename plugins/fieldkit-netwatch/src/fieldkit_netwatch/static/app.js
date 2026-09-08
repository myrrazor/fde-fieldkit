import { api, downloadText, esc } from "/fieldkit.js";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

const state = {
  token: null,
  status: null,
  sessions: [],
  ownedSessions: new Set(),
  report: null,
  overview: null,
  agents: [],
  policy: null,
  policyPath: "",
  policySaved: false,
  policyDirty: false,
  pollTimer: null,
};

bindNavigation();
bindEvidenceTabs();
bindTrafficFilters();
bindCaptureControls();
bindPolicyControls();
bindSessionControls();
$("#refresh-diagnostics").addEventListener("click", loadDiagnostics);
$("#refresh").addEventListener("click", () => refreshAll(true));
$("#session-select").addEventListener("change", async () => {
  syncSessionUrl();
  await loadSelectedReport(true);
});

bootstrap();

async function bootstrap() {
  showView(viewFromHash(), false);
  const jobs = await Promise.allSettled([
    loadControl(),
    loadDiagnostics(),
    loadAgents(),
    loadPolicy(),
    loadSessions(),
    loadOverview(),
  ]);
  const readable = [jobs[1], jobs[4], jobs[5]].some((job) => job.status === "fulfilled");
  if (!readable) {
    setFreshness("Local API unavailable", true);
    return;
  }
  await loadSelectedReport(false);
  setFreshness("Current now");
}

async function refreshAll(announced) {
  $("#refresh").disabled = true;
  setFreshness("Refreshing…");
  try {
    await Promise.all([loadSessions(), loadOverview(), loadAgents()]);
    await loadSelectedReport(false);
    setFreshness(announced ? `Updated ${timeOnly(new Date().toISOString())}` : "Current now");
  } catch (error) {
    setFreshness(error.message, true);
  } finally {
    $("#refresh").disabled = false;
    schedulePoll();
  }
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (!["starting", "running"].includes(state.report?.session.status)) return;
  state.pollTimer = window.setTimeout(() => refreshAll(false), 2000);
}

async function loadControl() {
  try {
    const payload = await api("/api/netwatch/control", { method: "GET" });
    state.token = payload.token;
    state.policyPath = payload.policy_path;
    renderControlState(true);
  } catch (error) {
    state.token = null;
    renderControlState(false, error.message);
  }
  updateControlAvailability();
}

function renderControlState(available, detail = "") {
  const element = $("#control-state");
  if (available) {
    element.innerHTML = `
      <strong>Local controls ready</strong>
      <p>This direct loopback browser may launch owned runs, attach processes, and edit the managed policy.</p>
      <button class="nw-btn nw-btn-small" type="button" data-open-view="system">Coverage details</button>`;
  } else {
    element.innerHTML = `
      <strong>Read-only evidence</strong>
      <p>${esc(detail || "Mutation controls require a direct loopback connection.")}</p>
      <button class="nw-btn nw-btn-small" type="button" data-open-view="system">Why controls are locked</button>`;
  }
  bindOpenViewButtons(element);
}

function updateControlAvailability() {
  for (const control of $$('[data-control-action]')) control.disabled = !state.token;
  const policyReady = Boolean(state.policy);
  const policyEditable = Boolean(state.token && policyReady);
  $("#policy-default").disabled = !policyEditable;
  for (const control of $$("#rule-form input, #rule-form select, #rule-form textarea, #rule-form button")) {
    control.disabled = !policyEditable;
  }
  for (const control of $$("#policy-check-form input, #policy-check-form select, #policy-check-form button")) {
    control.disabled = !policyEditable;
  }
  for (const control of $$("#policy-rules button")) control.disabled = !policyEditable;
  $("#save-policy").disabled = !policyEditable;
  $("#export-policy").disabled = !policyReady;
}

async function loadDiagnostics() {
  const payload = await api("/api/netwatch/status", { method: "GET" });
  state.status = payload;
  $("#storage-path").textContent = payload.storage;
  $("#top-status").textContent = payload.control_available ? "local control active" : "read-only evidence";
  const rows = [
    ["Platform", `${payload.platform.system} ${payload.platform.release} · ${payload.platform.machine}`],
    ["HTTP / CONNECT", availability(payload.capture.http_proxy, "available", "unavailable")],
    ["SOCKS5 TCP", availability(payload.capture.socks5_tcp, "available", "unavailable")],
    ["Attach snapshots", availability(payload.capture.attach_snapshot, "lsof available", "lsof unavailable")],
    ["Codex", agentCapability(payload.agents.codex, "network_proxy")],
    ["Claude Code", agentCapability(payload.agents.claude, "strict_sandbox_proxy")],
    ["TLS decryption", "Not performed. HTTPS content remains encrypted."],
    ["UDP / QUIC", "Not captured or enforced."],
    ["Whole machine", "Requires a separately signed macOS Network Extension."],
    ["Evidence DB", payload.storage],
  ];
  $("#capabilities").innerHTML = rows.map(([name, value]) => (
    `<li><strong>${esc(name)}</strong><span>${esc(value)}</span></li>`
  )).join("");
}

async function loadSessions() {
  const payload = await api("/api/netwatch/sessions", { method: "GET" });
  state.sessions = payload.sessions;
  state.ownedSessions = new Set(payload.owned_sessions || []);
  $("#storage-path").textContent = payload.storage;
  const select = $("#session-select");
  const previous = select.value;
  if (!state.sessions.length) {
    select.innerHTML = '<option value="">No sessions yet</option>';
    select.disabled = true;
    renderSessionOverview();
    return;
  }
  select.disabled = false;
  select.innerHTML = state.sessions.map((session) => (
    `<option value="${attr(session.id)}">${esc(sessionLabel(session))}</option>`
  )).join("");
  const requested = new URLSearchParams(window.location.search).get("session");
  const choice = [requested, previous].find((id) => state.sessions.some((row) => row.id === id));
  if (choice) select.value = choice;
  renderSessionOverview();
}

async function loadOverview() {
  state.overview = await api("/api/netwatch/overview", { method: "GET" });
  renderOverview();
}

async function loadAgents() {
  try {
    const payload = await api("/api/netwatch/agents", { method: "GET" });
    state.agents = payload.agents;
    renderAgents();
  } catch (error) {
    $("#running-agents").innerHTML = `<p class="nw-error">${esc(error.message)}</p>`;
  }
}

async function loadPolicy() {
  try {
    const payload = await api("/api/netwatch/policy", { method: "GET" });
    state.policy = payload.policy;
    state.policyPath = payload.path;
    state.policySaved = payload.saved;
    state.policyDirty = false;
    renderPolicy();
  } catch (error) {
    state.policy = null;
    state.policySaved = false;
    state.policyDirty = false;
    $("#policy-path").textContent = state.policyPath || "managed policy";
    $("#policy-save-state").textContent = "Policy needs repair";
    $("#policy-rules").innerHTML = `<p class="nw-error">${esc(error.message)} Import a valid policy JSON file to repair it.</p>`;
    $("#rule-state").textContent = "Import remains available because this browser still has local control.";
    $("#rule-state").dataset.kind = "error";
  }
  updateControlAvailability();
  updateTerminalCommand();
}

async function loadSelectedReport(announced) {
  clearTimeout(state.pollTimer);
  const sessionId = $("#session-select").value;
  if (!sessionId) {
    state.report = null;
    renderReport();
    return;
  }
  try {
    state.report = await api(`/api/netwatch/sessions/${encodeURIComponent(sessionId)}`, { method: "GET" });
    renderReport();
    if (announced) setFreshness(`Session loaded ${timeOnly(new Date().toISOString())}`);
    schedulePoll();
  } catch (error) {
    state.report = null;
    $("#session-summary").innerHTML = `<p class="nw-error">${esc(error.message)}</p>`;
    setFreshness("Session load failed", true);
  }
}

function renderOverview() {
  if (!state.overview) return;
  const totals = state.overview.totals;
  $("#overview-stats").innerHTML = statsMarkup([
    [totals.sessions, "saved sessions"],
    [totals.running, "running now"],
    [totals.events, "captured records"],
    [totals.blocked, "blocked"],
    [totals.services, "identified services"],
    [formatBytes(totals.bytes_sent + totals.bytes_received), "relayed bytes"],
  ]);
  $("#source-overview").innerHTML = breakdownTable(state.overview.sources, "source");
  $("#agent-overview").innerHTML = breakdownTable(state.overview.agents, "agent");
  $("#destination-overview").innerHTML = aggregateDestinationsTable(state.overview.destinations);
  renderSessionOverview();
}

function breakdownTable(rows, key) {
  if (!rows.length) return '<p class="nw-empty">No captured source records yet.</p>';
  const body = rows.map((row) => `
    <tr>
      <td><span class="nw-source-mark">${esc(displaySource(row[key]))}</span></td>
      <td class="num">${number(row.events)}</td>
      <td class="num">${number(row.blocked)}</td>
      <td class="num nw-compact-hide">${number(row.would_block)}</td>
      <td class="num nw-compact-hide">${esc(formatBytes(row.bytes_sent + row.bytes_received))}</td>
    </tr>`).join("");
  const label = key === "agent" ? "Agent" : "Source";
  return ledger([label, "Records", "Blocked", "Would block", "Bytes"], body, ["", "num", "num", "num nw-compact-hide", "num nw-compact-hide"]);
}

function aggregateDestinationsTable(rows) {
  if (!rows.length) return '<p class="nw-empty">No destinations have been recorded.</p>';
  const body = rows.map((row) => `
    <tr>
      <td>${esc(row.service)}<span class="path-list">${esc(row.agents.join(", "))}</span></td>
      <td class="mono">${esc(row.host)}:${esc(row.port)}</td>
      <td>${esc(row.protocol)} / ${esc(row.scope)}</td>
      <td class="nw-compact-hide">${esc(row.sources.map(displaySource).join(", "))}</td>
      <td class="num">${number(row.events)}</td>
      <td>${aggregateOutcome(row)}</td>
      <td class="row-actions nw-compact-hide">
        <button class="nw-btn nw-btn-small" type="button" data-quick-rule="allow" data-host="${attr(row.host)}" data-port="${attr(row.port)}" data-protocol="${attr(row.protocol)}" data-scope="${attr(row.scope)}">Allow</button>
        <button class="nw-btn nw-btn-small nw-btn-danger" type="button" data-quick-rule="deny" data-host="${attr(row.host)}" data-port="${attr(row.port)}" data-protocol="${attr(row.protocol)}" data-scope="${attr(row.scope)}">Deny</button>
      </td>
    </tr>`).join("");
  return ledger(["Service / agents", "Destination", "Protocol / scope", "Capture", "Records", "Outcome", "Next-run policy"], body, ["", "", "", "nw-compact-hide", "num", "", "nw-compact-hide"]);
}

function renderSessionOverview() {
  const host = $("#session-overview");
  if (!host) return;
  if (!state.sessions.length) {
    host.innerHTML = '<p class="nw-empty">No sessions yet. Start a supervised command or attach to a running agent.</p>';
    return;
  }
  const body = state.sessions.map((session) => `
    <tr>
      <td><button class="nw-btn nw-btn-small" type="button" data-session-id="${attr(session.id)}">Open</button></td>
      <td>${esc(dateTime(session.started_at))}</td>
      <td>${esc(session.agent)}</td>
      <td>${esc(session.mode)}</td>
      <td><span class="nw-status ${attr(session.status)}">${esc(session.status)}</span></td>
      <td class="mono nw-compact-hide">${esc(session.command.join(" "))}</td>
    </tr>`).join("");
  host.innerHTML = ledger(["", "Started", "Agent", "Mode", "Status", "Executable"], body, ["", "", "", "", "", "nw-compact-hide"]);
}

function renderReport() {
  const report = state.report;
  if (!report) {
    $("#session-summary").innerHTML = '<p class="nw-empty">Select a session to inspect its evidence.</p>';
    $("#destinations").innerHTML = '<p class="nw-empty">No session selected.</p>';
    $("#events").innerHTML = '<p class="nw-empty">No session selected.</p>';
    $("#tool-events").innerHTML = '<p class="nw-empty">No session selected.</p>';
    $("#coverage").innerHTML = '<p class="nw-empty">No session selected.</p>';
    updateSessionActions();
    return;
  }
  const session = report.session;
  $("#session-summary").innerHTML = `
    <div class="nw-stats">${statsMarkup([
      [report.totals.events, "captured records"],
      [report.totals.services, "services"],
      [report.totals.blocked, "blocked"],
      [report.totals.would_block, "would block"],
      [report.totals.tool_events, "tool actions"],
      [formatBytes(report.totals.bytes_sent + report.totals.bytes_received), "relayed bytes"],
    ])}</div>
    <div class="nw-section-head"><h2>${esc(session.agent)} · <span class="nw-status ${attr(session.status)}">${esc(session.status)}</span></h2><span>${esc(session.id)}</span></div>
    <div class="nw-policy-state" style="margin-top: 10px">
      <span>Mode <code>${esc(session.mode)}</code></span>
      <span>PID <code>${esc(session.root_pid ?? "not recorded")}</code></span>
      <span>Started <code>${esc(dateTime(session.started_at))}</code></span>
      <span>Ended <code>${esc(session.ended_at ? dateTime(session.ended_at) : "still running")}</code></span>
      <span>Executable <code>${esc(session.command.join(" "))}</code></span>
      <span>Exit <code>${esc(session.exit_code ?? "—")}</code></span>
    </div>`;
  populateFilterOptions();
  renderFilteredEvidence();
  $("#coverage").innerHTML = `
    <ul class="nw-capability-list">
      ${session.coverage.map((item) => `<li><strong>Active path</strong><span>${esc(item)}</span></li>`).join("")}
      ${session.note ? `<li><strong>Coverage note</strong><span>${esc(session.note)}</span></li>` : ""}
      <li><strong>HTTP proxy</strong><span>${esc(session.http_proxy || "not recorded")}</span></li>
      <li><strong>SOCKS proxy</strong><span>${esc(session.socks_proxy || "not recorded")}</span></li>
      <li><strong>Policy at start</strong><span>${esc(session.policy_path || "built-in audit-all policy")}</span></li>
    </ul>`;
  updateSessionActions();
}

function renderFilteredEvidence() {
  if (!state.report) return;
  const search = $("#traffic-search").value.trim().toLowerCase();
  const decision = $("#decision-filter").value;
  const source = $("#source-filter").value;
  const scope = $("#scope-filter").value;
  const eventRows = state.report.events.filter((row) => {
    const text = `${row.service} ${row.host} ${row.path || ""}`.toLowerCase();
    return (!search || text.includes(search))
      && (!decision || row.decision === decision)
      && (!source || row.source === source)
      && (!scope || row.scope === scope);
  });
  const destinationRows = state.report.destinations.filter((row) => {
    const text = `${row.service} ${row.host} ${(row.paths || []).join(" ")}`.toLowerCase();
    return (!search || text.includes(search))
      && (!scope || row.scope === scope)
      && (!decision || destinationHasDecision(row, decision));
  });
  renderDestinations(destinationRows);
  renderEvents(eventRows);
  renderToolEvents(search);
}

function renderDestinations(rows) {
  if (!rows.length) {
    $("#destinations").innerHTML = '<p class="nw-empty">No destination groups match these filters.</p>';
    return;
  }
  const body = rows.map((row) => `
    <tr>
      <td>${esc(row.service)}<span class="path-list">${esc((row.paths || []).join(" · "))}</span></td>
      <td class="mono">${esc(row.host)}:${esc(row.port)}</td>
      <td>${esc(row.protocol)} / ${esc(row.scope)}</td>
      <td class="num">${number(row.events)}</td>
      <td>${aggregateOutcome(row)}</td>
      <td class="num nw-compact-hide">${esc(formatBytes(row.bytes_sent + row.bytes_received))}</td>
      <td class="nw-compact-hide">${esc(timeOnly(row.first_seen))}<br>${esc(timeOnly(row.last_seen))}</td>
      <td class="row-actions nw-compact-hide"><button class="nw-btn nw-btn-small" type="button" data-quick-rule="allow" data-host="${attr(row.host)}" data-port="${attr(row.port)}" data-protocol="${attr(row.protocol)}" data-scope="${attr(row.scope)}">Allow</button> <button class="nw-btn nw-btn-small nw-btn-danger" type="button" data-quick-rule="deny" data-host="${attr(row.host)}" data-port="${attr(row.port)}" data-protocol="${attr(row.protocol)}" data-scope="${attr(row.scope)}">Deny</button></td>
    </tr>`).join("");
  $("#destinations").innerHTML = ledger(["Service / paths", "Destination", "Protocol / scope", "Records", "Outcome", "Bytes", "First / last", "Next-run policy"], body, ["", "", "", "num", "", "num nw-compact-hide", "nw-compact-hide", "nw-compact-hide"]);
}

function renderEvents(rows) {
  if (!rows.length) {
    $("#events").innerHTML = '<p class="nw-empty">No raw events match these filters.</p>';
    return;
  }
  const body = rows.map((row) => `
    <tr>
      <td>${esc(timeOnly(row.started_at))}</td>
      <td><span class="nw-source-mark">${esc(displaySource(row.source))}</span></td>
      <td>${esc(row.service)}<span class="path-list">${esc(row.host)}:${esc(row.port)}${row.path ? ` · ${esc(row.path)}` : ""}</span></td>
      <td><span class="nw-status ${attr(row.decision)}">${esc(row.decision.replace("_", " "))}</span></td>
      <td class="nw-compact-hide">${esc(row.rule_id || "—")}</td>
      <td class="mono nw-compact-hide">${esc(row.resolved_ip || "unresolved")}</td>
      <td class="num nw-compact-hide">${esc(formatBytes(row.bytes_sent + row.bytes_received))}</td>
      <td class="nw-compact-hide">${esc(row.detail || "")}</td>
    </tr>`).join("");
  $("#events").innerHTML = ledger(["Time", "Capture", "Service / destination", "Decision", "Rule", "Resolved IP", "Bytes", "Detail"], body, ["", "", "", "", "nw-compact-hide", "nw-compact-hide", "num nw-compact-hide", "nw-compact-hide"]);
}

function renderToolEvents(search) {
  const rows = state.report.tool_events.filter((row) => {
    const text = `${row.tool} ${row.target || ""} ${row.event}`.toLowerCase();
    return !search || text.includes(search);
  });
  if (!rows.length) {
    $("#tool-events").innerHTML = '<p class="nw-empty">No supported hook reported a matching tool action. These records are separate from network events.</p>';
    return;
  }
  const body = rows.map((row) => `
    <tr><td>${esc(timeOnly(row.occurred_at))}</td><td>${esc(row.event)}</td><td class="mono">${esc(row.tool)}</td><td>${esc(row.target || "—")}</td><td class="mono nw-compact-hide">${esc(row.correlation_id || "—")}</td></tr>`).join("");
  $("#tool-events").innerHTML = ledger(["Time", "Event", "Tool", "Sanitized target", "Correlation"], body, ["", "", "", "", "nw-compact-hide"]);
}

function renderAgents() {
  if (!state.agents.length) {
    $("#running-agents").innerHTML = '<p class="nw-empty">No running Codex or Claude root process was found. Generic processes can still be attached by PID.</p>';
    return;
  }
  const body = state.agents.map((agent) => `
    <tr><td class="num">${esc(agent.pid)}</td><td>${esc(agent.agent)}</td><td class="mono">${esc(agent.executable)}</td><td class="nw-compact-hide">${esc(agent.command)}</td><td class="row-actions"><button class="nw-btn nw-btn-small" type="button" data-use-pid="${attr(agent.pid)}">Use PID</button></td></tr>`).join("");
  $("#running-agents").innerHTML = ledger(["PID", "Agent", "Executable", "Command", ""], body, ["num", "", "", "nw-compact-hide", ""]);
}

function renderPolicy() {
  if (!state.policy) return;
  $("#policy-default").value = state.policy.default;
  $("#policy-path").textContent = state.policyPath;
  $("#policy-save-state").textContent = state.policyDirty
    ? "Unsaved changes"
    : state.policySaved ? "Saved policy" : "Starter policy, not saved yet";
  const rules = state.policy.rules || [];
  if (!rules.length) {
    $("#policy-rules").innerHTML = '<p class="nw-empty">No rules. The default action will apply to public destinations; restricted scopes still need explicit private access.</p>';
    updateControlAvailability();
    return;
  }
  const body = rules.map((rule, index) => `
    <tr>
      <td class="num">${index + 1}</td>
      <td class="mono">${esc(rule.id)}</td>
      <td><span class="nw-status ${attr(rule.action === "deny" ? "blocked" : "allowed")}">${esc(rule.action)}</span></td>
      <td>${ruleSelectors(rule)}</td>
      <td>${rule.allow_private ? "private allowed" : "public only"}</td>
      <td class="nw-compact-hide">${esc(rule.note || "")}</td>
      <td class="row-actions">
        <button class="nw-btn nw-btn-small" type="button" data-rule-move="up" data-rule-index="${index}" aria-label="Move ${attr(rule.id)} up">↑</button>
        <button class="nw-btn nw-btn-small" type="button" data-rule-move="down" data-rule-index="${index}" aria-label="Move ${attr(rule.id)} down">↓</button>
        <button class="nw-btn nw-btn-small" type="button" data-rule-edit="${index}">Edit</button>
        <button class="nw-btn nw-btn-small nw-btn-danger" type="button" data-rule-delete="${index}">Delete</button>
      </td>
    </tr>`).join("");
  $("#policy-rules").innerHTML = ledger(["Order", "ID", "Action", "Matches", "Network", "Reason", ""], body, ["num", "", "", "", "", "nw-compact-hide", ""]);
  updateControlAvailability();
}

function bindNavigation() {
  for (const button of $$('[data-view]')) {
    button.addEventListener("click", () => showView(button.dataset.view));
  }
  bindOpenViewButtons(document);
  window.addEventListener("hashchange", () => showView(viewFromHash(), false));
}

function bindOpenViewButtons(root) {
  for (const button of root.querySelectorAll("[data-open-view]")) {
    if (button.dataset.bound === "true") continue;
    button.dataset.bound = "true";
    button.addEventListener("click", () => showView(button.dataset.openView));
  }
}

function showView(name, updateHash = true) {
  const valid = ["overview", "traffic", "capture", "policy", "system"];
  const selected = valid.includes(name) ? name : "overview";
  for (const panel of $$('[data-view-panel]')) panel.hidden = panel.dataset.viewPanel !== selected;
  for (const button of $$('[data-view]')) {
    if (button.dataset.view === selected) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  if (updateHash) window.history.replaceState({}, "", `${window.location.pathname}${window.location.search}#${selected}`);
  $("#workspace").focus({ preventScroll: true });
}

function viewFromHash() {
  return window.location.hash.replace("#", "") || "overview";
}

function bindEvidenceTabs() {
  const tabs = $$('[data-evidence-tab]');
  for (const [index, tab] of tabs.entries()) {
    tab.addEventListener("click", () => activateEvidenceTab(tab));
    tab.addEventListener("keydown", (event) => {
      let target = null;
      if (event.key === "ArrowRight") target = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") target = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") target = 0;
      if (event.key === "End") target = tabs.length - 1;
      if (target === null) return;
      event.preventDefault();
      activateEvidenceTab(tabs[target], true);
    });
  }
}

function activateEvidenceTab(tab, focus = false) {
  const selected = tab.dataset.evidenceTab;
  for (const candidate of $$('[data-evidence-tab]')) {
    const active = candidate === tab;
    candidate.setAttribute("aria-selected", String(active));
    candidate.tabIndex = active ? 0 : -1;
  }
  for (const panel of $$('.nw-tabpanel')) panel.hidden = panel.id !== `panel-${selected}`;
  if (focus) tab.focus();
}

function bindTrafficFilters() {
  for (const control of [$("#traffic-search"), $("#decision-filter"), $("#source-filter"), $("#scope-filter")]) {
    control.addEventListener(control.tagName === "INPUT" ? "input" : "change", renderFilteredEvidence);
  }
}

function bindCaptureControls() {
  $("#run-form").addEventListener("submit", startRun);
  $("#attach-form").addEventListener("submit", startAttach);
  $("#run-command").addEventListener("input", updateTerminalCommand);
  $("#run-agent").addEventListener("change", updateTerminalCommand);
  $("#run-mode").addEventListener("change", updateTerminalCommand);
  $("#run-policy").addEventListener("change", updateTerminalCommand);
  $("#copy-terminal-command").addEventListener("click", async () => {
    await copyText($("#terminal-command").textContent);
    $("#run-state").textContent = "Terminal command copied.";
  });
  $("#running-agents").addEventListener("click", (event) => {
    const button = event.target.closest("[data-use-pid]");
    if (!button) return;
    $("#attach-pid").value = button.dataset.usePid;
    $("#attach-pid").focus();
  });
}

async function startRun(event) {
  event.preventDefault();
  const feedback = $("#run-state");
  try {
    const command = splitCommandLine($("#run-command").value);
    feedback.textContent = "Starting local proxies and command…";
    feedback.dataset.kind = "";
    const payload = await mutate("/api/netwatch/runs", {
      method: "POST",
      body: {
        command,
        mode: $("#run-mode").value,
        agent: $("#run-agent").value,
        use_policy: $("#run-policy").checked,
      },
    });
    feedback.textContent = `Session ${payload.session.id} started.`;
    feedback.dataset.kind = "success";
    await refreshAll(false);
    $("#session-select").value = payload.session.id;
    syncSessionUrl();
    await loadSelectedReport(false);
    showView("traffic");
  } catch (error) {
    feedback.textContent = error.message;
    feedback.dataset.kind = "error";
  }
}

async function startAttach(event) {
  event.preventDefault();
  const feedback = $("#attach-state");
  try {
    feedback.textContent = "Starting observation…";
    feedback.dataset.kind = "";
    const payload = await mutate("/api/netwatch/attachments", {
      method: "POST",
      body: {
        pid: Number($("#attach-pid").value),
        follow: $("#attach-follow").checked,
        interval: Number($("#attach-interval").value),
      },
    });
    feedback.textContent = `Observation session ${payload.session.id} started.`;
    feedback.dataset.kind = "success";
    await refreshAll(false);
    $("#session-select").value = payload.session.id;
    syncSessionUrl();
    await loadSelectedReport(false);
    showView("traffic");
  } catch (error) {
    feedback.textContent = error.message;
    feedback.dataset.kind = "error";
  }
}

function bindPolicyControls() {
  $("#policy-default").addEventListener("change", () => {
    if (!state.policy) return;
    state.policy.default = $("#policy-default").value;
    markPolicyDirty();
  });
  $("#rule-form").addEventListener("submit", saveRuleDraft);
  $("#cancel-rule").addEventListener("click", resetRuleForm);
  $("#save-policy").addEventListener("click", savePolicy);
  $("#import-policy").addEventListener("click", () => $("#policy-file").click());
  $("#policy-file").addEventListener("change", importPolicy);
  $("#export-policy").addEventListener("click", () => {
    if (!state.policy) return;
    downloadText("netwatch-policy.json", `${JSON.stringify(state.policy, null, 2)}\n`);
  });
  $("#policy-check-form").addEventListener("submit", checkPolicy);
  $("#policy-rules").addEventListener("click", handleRuleAction);
  $("#destination-overview").addEventListener("click", handleQuickRule);
  $("#destinations").addEventListener("click", handleQuickRule);
}

function saveRuleDraft(event) {
  event.preventDefault();
  const feedback = $("#rule-state");
  try {
    if (!state.policy) throw new Error("Import a valid policy before editing rules.");
    const indexValue = $("#rule-index").value;
    const rule = ruleFromForm();
    const duplicate = state.policy.rules.findIndex((item, index) => item.id === rule.id && String(index) !== indexValue);
    if (duplicate >= 0) throw new Error(`Rule ID ${rule.id} already exists.`);
    if (indexValue === "") state.policy.rules.push(rule);
    else state.policy.rules[Number(indexValue)] = rule;
    markPolicyDirty();
    renderPolicy();
    resetRuleForm();
    feedback.textContent = indexValue === "" ? "Rule added. Save the policy to use it." : "Rule updated. Save the policy to use it.";
    feedback.dataset.kind = "success";
  } catch (error) {
    feedback.textContent = error.message;
    feedback.dataset.kind = "error";
  }
}

function ruleFromForm() {
  const rule = {
    id: $("#rule-id").value.trim(),
    action: $("#rule-action").value,
  };
  if (!rule.id) throw new Error("Rule ID is required.");
  const hosts = listValues($("#rule-hosts").value);
  const ips = listValues($("#rule-ips").value);
  const rawPorts = listValues($("#rule-ports").value);
  const ports = rawPorts.map(Number);
  if (ports.some((port) => !Number.isInteger(port) || port < 1 || port > 65535)) throw new Error("Ports must be whole numbers from 1 through 65535.");
  const protocols = $$('input[name="rule-protocol"]:checked').map((input) => input.value);
  if (!hosts.length && !ips.length && !ports.length && !protocols.length) throw new Error("Add at least one host, IP/CIDR, port, or protocol matcher.");
  if (hosts.length) rule.hosts = hosts;
  if (ips.length) rule.ips = ips;
  if (ports.length) rule.ports = ports;
  if (protocols.length) rule.protocols = protocols;
  if ($("#rule-private").checked) {
    if (rule.action !== "allow") throw new Error("Private access can only be enabled on an allow rule.");
    rule.allow_private = true;
  }
  const note = $("#rule-note").value.trim();
  if (note) rule.note = note;
  return rule;
}

function handleRuleAction(event) {
  const edit = event.target.closest("[data-rule-edit]");
  const remove = event.target.closest("[data-rule-delete]");
  const move = event.target.closest("[data-rule-move]");
  if (edit) editRule(Number(edit.dataset.ruleEdit));
  if (remove) {
    const index = Number(remove.dataset.ruleDelete);
    const rule = state.policy.rules[index];
    if (window.confirm(`Delete rule ${rule.id}? The change is not active until you save.`)) {
      state.policy.rules.splice(index, 1);
      markPolicyDirty();
      renderPolicy();
    }
  }
  if (move) moveRule(Number(move.dataset.ruleIndex), move.dataset.ruleMove);
}

function editRule(index) {
  const rule = state.policy.rules[index];
  $("#rule-index").value = String(index);
  $("#rule-id").value = rule.id;
  $("#rule-action").value = rule.action;
  $("#rule-hosts").value = (rule.hosts || []).join("\n");
  $("#rule-ips").value = (rule.ips || []).join("\n");
  $("#rule-ports").value = (rule.ports || []).join(", ");
  for (const input of $$('input[name="rule-protocol"]')) input.checked = (rule.protocols || []).includes(input.value);
  $("#rule-private").checked = Boolean(rule.allow_private);
  $("#rule-note").value = rule.note || "";
  $("#rule-form-title").textContent = `Edit ${rule.id}`;
  $("#rule-form button[type=submit]").textContent = "Update rule";
  $("#cancel-rule").hidden = false;
  $("#rule-id").focus();
}

function moveRule(index, direction) {
  const target = direction === "up" ? index - 1 : index + 1;
  if (target < 0 || target >= state.policy.rules.length) return;
  [state.policy.rules[index], state.policy.rules[target]] = [state.policy.rules[target], state.policy.rules[index]];
  markPolicyDirty();
  renderPolicy();
}

function resetRuleForm() {
  $("#rule-form").reset();
  $("#rule-index").value = "";
  $("#rule-form-title").textContent = "Add a rule";
  $("#rule-form button[type=submit]").textContent = "Add rule";
  $("#cancel-rule").hidden = true;
}

async function savePolicy() {
  try {
    if (!state.policy) throw new Error("Import a valid policy before saving.");
    const payload = await mutate("/api/netwatch/policy", { method: "PUT", body: state.policy });
    state.policy = payload.policy;
    state.policyPath = payload.path;
    state.policySaved = payload.saved;
    state.policyDirty = false;
    renderPolicy();
    updateControlAvailability();
    updateTerminalCommand();
    $("#rule-state").textContent = "Policy saved. It will apply to future supervised runs.";
    $("#rule-state").dataset.kind = "success";
  } catch (error) {
    $("#rule-state").textContent = error.message;
    $("#rule-state").dataset.kind = "error";
  }
}

async function importPolicy() {
  const file = $("#policy-file").files[0];
  if (!file) return;
  try {
    const payload = JSON.parse(await file.text());
    const validated = await mutate("/api/netwatch/policy/validate", {
      method: "POST",
      body: payload,
    });
    state.policy = validated.policy;
    markPolicyDirty();
    renderPolicy();
    updateControlAvailability();
    $("#rule-state").textContent = `Imported ${file.name}. Review and save it to activate.`;
    $("#rule-state").dataset.kind = "success";
  } catch (error) {
    $("#rule-state").textContent = `Import failed: ${error.message}`;
    $("#rule-state").dataset.kind = "error";
  } finally {
    $("#policy-file").value = "";
  }
}

async function checkPolicy(event) {
  event.preventDefault();
  const host = $("#policy-decision");
  host.innerHTML = '<p class="nw-loading">Resolving and evaluating…</p>';
  try {
    const payload = await mutate("/api/netwatch/policy/check", {
      method: "POST",
      body: {
        destination: $("#check-destination").value,
        protocol: $("#check-protocol").value,
        mode: $("#check-mode").value,
      },
    });
    const row = payload.selected;
    const addressRows = payload.addresses.map((address) => `
      <tr>
        <td class="mono">${esc(address.ip || "unresolved")}</td>
        <td>${esc(address.scope)}</td>
        <td><span class="nw-status ${attr(address.outcome)}">${esc(address.outcome.replace("_", " "))}</span></td>
        <td class="mono">${esc(address.rule_id || "—")}</td>
        <td>${esc(address.reason)}</td>
      </tr>`).join("");
    host.innerHTML = `<div class="nw-decision"><strong><span class="nw-status ${attr(row.outcome)}">${esc(row.outcome.replace("_", " "))}</span> · ${esc(payload.destination.host)}:${esc(payload.destination.port)}</strong><p>${esc(row.reason)}${row.ip ? ` · ${esc(row.ip)} (${esc(row.scope)})` : " · unresolved"}</p></div>${ledger(["Resolved IP", "Scope", "Outcome", "Rule", "Reason"], addressRows, ["mono", "", "", "mono", ""])}`;
  } catch (error) {
    host.innerHTML = `<p class="nw-error">${esc(error.message)}</p>`;
  }
}

function handleQuickRule(event) {
  const button = event.target.closest("[data-quick-rule]");
  if (!button) return;
  showView("policy");
  if (!state.policy) {
    $("#rule-state").textContent = "Import a valid policy before adding a destination rule.";
    $("#rule-state").dataset.kind = "error";
    return;
  }
  resetRuleForm();
  const action = button.dataset.quickRule;
  const host = button.dataset.host;
  $("#rule-id").value = `${action}-${slug(host)}`;
  $("#rule-action").value = action;
  $("#rule-hosts").value = host;
  $("#rule-ports").value = button.dataset.port;
  const protocol = button.dataset.protocol;
  for (const input of $$('input[name="rule-protocol"]')) input.checked = input.value === protocol;
  $("#rule-private").checked = action === "allow" && button.dataset.scope !== "public";
  $("#rule-note").value = `Added from observed ${button.dataset.scope} destination`;
  $("#rule-id").focus();
  $("#rule-state").textContent = "Review the prefilled rule, add it, then save the policy. Existing tunnels are unchanged.";
}

function markPolicyDirty() {
  state.policyDirty = true;
  $("#policy-save-state").textContent = "Unsaved changes";
}

function bindSessionControls() {
  $("#session-overview").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-session-id]");
    if (!button) return;
    $("#session-select").value = button.dataset.sessionId;
    syncSessionUrl();
    await loadSelectedReport(false);
    showView("traffic");
  });
  $("#stop-session").addEventListener("click", stopSelectedSession);
  $("#delete-session").addEventListener("click", deleteSelectedSession);
  for (const link of [$("#export-json"), $("#export-csv")]) {
    link.addEventListener("click", (event) => {
      if (link.getAttribute("aria-disabled") === "true") event.preventDefault();
    });
  }
}

async function stopSelectedSession() {
  if (!state.report) return;
  const feedback = $("#session-action-state");
  try {
    feedback.textContent = "Stopping the owned command and its process group…";
    await mutate(`/api/netwatch/sessions/${encodeURIComponent(state.report.session.id)}/stop`, { method: "POST", body: {} });
    feedback.textContent = "Session stopped.";
    feedback.dataset.kind = "success";
    await refreshAll(false);
  } catch (error) {
    feedback.textContent = error.message;
    feedback.dataset.kind = "error";
  }
}

async function deleteSelectedSession() {
  if (!state.report) return;
  const session = state.report.session;
  if (!window.confirm(`Delete session ${session.id} and its local evidence? This cannot be undone.`)) return;
  const feedback = $("#session-action-state");
  try {
    await mutate(`/api/netwatch/sessions/${encodeURIComponent(session.id)}`, { method: "DELETE", body: {} });
    state.report = null;
    feedback.textContent = "Session evidence deleted.";
    await refreshAll(false);
    showView("overview");
  } catch (error) {
    feedback.textContent = error.message;
    feedback.dataset.kind = "error";
  }
}

function updateSessionActions() {
  const session = state.report?.session;
  const owned = session && state.ownedSessions.has(session.id);
  $("#stop-session").disabled = !owned || !["starting", "running"].includes(session.status);
  $("#delete-session").disabled = !session || ["starting", "running"].includes(session.status) || !state.token;
  const id = session?.id || "";
  const links = [
    [$("#export-json"), id ? `/api/netwatch/sessions/${encodeURIComponent(id)}/export.json` : ""],
    [$("#export-csv"), id ? `/api/netwatch/sessions/${encodeURIComponent(id)}/export.csv` : ""],
  ];
  for (const [link, url] of links) {
    if (url) link.href = url;
    else link.removeAttribute("href");
    link.tabIndex = url ? 0 : -1;
    link.setAttribute("aria-disabled", String(!url));
  }
}

function populateFilterOptions() {
  const sources = [...new Set(state.report.events.map((row) => row.source))].sort();
  const scopes = [...new Set(state.report.events.map((row) => row.scope))].sort();
  preserveSelectOptions($("#source-filter"), sources, "All sources");
  preserveSelectOptions($("#scope-filter"), scopes, "All scopes");
}

function preserveSelectOptions(select, values, allLabel) {
  const current = select.value;
  select.innerHTML = `<option value="">${esc(allLabel)}</option>${values.map((value) => `<option value="${attr(value)}">${esc(displaySource(value))}</option>`).join("")}`;
  if (values.includes(current)) select.value = current;
}

function updateTerminalCommand() {
  let command;
  try {
    command = splitCommandLine($("#run-command").value || "codex");
  } catch {
    command = [$("#run-command").value || "codex"];
  }
  const parts = ["fieldkit", "netwatch", "run", "--mode", $("#run-mode").value];
  if ($("#run-agent").value !== "auto") parts.push("--agent", $("#run-agent").value);
  const usesPolicy = $("#run-mode").value === "enforce" || $("#run-policy").checked;
  if (usesPolicy && state.policySaved) parts.push("--policy", state.policyPath);
  parts.push("--", ...command);
  $("#terminal-command").textContent = parts.map(shellQuote).join(" ");
}

async function mutate(url, { method, body }) {
  if (!state.token) throw new Error("Local controls are locked. Open Fieldkit directly on localhost or 127.0.0.1.");
  return api(url, {
    method,
    body: JSON.stringify(body),
    headers: {
      "Content-Type": "application/json",
      "X-Fieldkit-Control": state.token,
    },
  });
}

function syncSessionUrl() {
  const url = new URL(window.location.href);
  if ($("#session-select").value) url.searchParams.set("session", $("#session-select").value);
  else url.searchParams.delete("session");
  window.history.replaceState({}, "", url);
}

function statsMarkup(rows) {
  return rows.map(([value, label]) => `<div class="nw-stat"><strong>${typeof value === "number" ? number(value) : esc(value)}</strong><span>${esc(label)}</span></div>`).join("");
}

function ledger(headers, body, classes = []) {
  const head = headers.map((header, index) => `<th scope="col" class="${classes[index] || ""}">${esc(header)}</th>`).join("");
  return `<div class="nw-tablewrap"><table class="nw-ledger"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function aggregateOutcome(row) {
  if (row.blocked) return `<span class="nw-status blocked">blocked ${number(row.blocked)}</span>`;
  if (row.would_block) return `<span class="nw-status would_block">would block ${number(row.would_block)}</span>`;
  if (row.unsupported) return `<span class="nw-status unsupported">unsupported ${number(row.unsupported)}</span>`;
  if (row.failed) return `<span class="nw-status failed">failed ${number(row.failed)}</span>`;
  if (row.observed) return `<span class="nw-status observed">observed ${number(row.observed)}</span>`;
  return `<span class="nw-status allowed">allowed ${number(row.allowed)}</span>`;
}

function destinationHasDecision(row, decision) {
  return Number(row[decision] || 0) > 0;
}

function ruleSelectors(rule) {
  const parts = [];
  if (rule.hosts?.length) parts.push(`host ${rule.hosts.join(", ")}`);
  if (rule.ips?.length) parts.push(`IP ${rule.ips.join(", ")}`);
  if (rule.ports?.length) parts.push(`port ${rule.ports.join(", ")}`);
  if (rule.protocols?.length) parts.push(rule.protocols.join(", "));
  return esc(parts.join(" · "));
}

function sessionLabel(session) {
  return `${timeOnly(session.started_at)} · ${session.agent} · ${session.mode} · ${session.status}`;
}

function displaySource(value) {
  const names = {
    "http-forward": "HTTP request",
    "http-connect": "HTTPS tunnel",
    socks5: "SOCKS5 tunnel",
    lsof: "Socket snapshot",
    "agent-hook": "Agent hook",
  };
  return names[value] || value;
}

function availability(value, yes, no) {
  return value ? yes : no;
}

function agentCapability(agent, capability) {
  if (!agent.path) return "Not found on PATH.";
  const detail = agent[capability] ? "strong proxy integration available" : "proxy environment fallback";
  return `${agent.path} · ${detail}${agent.version ? ` · ${agent.version}` : ""}`;
}

function dateTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleString();
}

function timeOnly(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function formatBytes(value) {
  const amount = Number(value || 0);
  if (amount < 1024) return `${amount} B`;
  if (amount < 1024 * 1024) return `${(amount / 1024).toFixed(1)} KiB`;
  if (amount < 1024 * 1024 * 1024) return `${(amount / 1024 / 1024).toFixed(1)} MiB`;
  return `${(amount / 1024 / 1024 / 1024).toFixed(1)} GiB`;
}

function number(value) {
  return Number(value || 0).toLocaleString();
}

function attr(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function listValues(value) {
  return value.split(/[\n,]+/).map((item) => item.trim()).filter(Boolean);
}

function slug(value) {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "destination";
}

function splitCommandLine(value) {
  const parts = [];
  let current = "";
  let quote = null;
  let escaped = false;
  for (const character of value.trim()) {
    if (escaped) {
      current += character;
      escaped = false;
    } else if (character === "\\" && quote !== "'") {
      escaped = true;
    } else if (quote) {
      if (character === quote) quote = null;
      else current += character;
    } else if (character === "'" || character === '"') {
      quote = character;
    } else if (/\s/.test(character)) {
      if (current) {
        parts.push(current);
        current = "";
      }
    } else {
      current += character;
    }
  }
  if (escaped || quote) throw new Error("Command has an unfinished quote or escape.");
  if (current) parts.push(current);
  if (!parts.length) throw new Error("Command needs an executable.");
  return parts;
}

function shellQuote(value) {
  if (/^[A-Za-z0-9_./:@%+=,-]+$/.test(value)) return value;
  return `'${value.replaceAll("'", "'\"'\"'")}'`;
}

async function copyText(value) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const input = document.createElement("textarea");
  input.value = value;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();
  const copied = document.execCommand("copy");
  input.remove();
  if (!copied) throw new Error("Clipboard access failed. Select the command manually.");
}

function setFreshness(message, error = false) {
  $("#freshness").textContent = message;
  $("#freshness").style.color = error ? "var(--danger)" : "";
}
