import {
  api,
  downloadText,
  dropzone,
  esc,
  renderTable,
  toast,
  withBusy,
} from "/fieldkit.js";

const draft = document.getElementById("draft");
const drop = document.getElementById("tell-drop");
const charCount = document.getElementById("char-count");
const sourceNote = document.getElementById("source-note");
const adapterLine = document.getElementById("adapter-line");
const egressWarning = document.getElementById("egress-warning");
const offline = document.getElementById("offline");
const ml = document.getElementById("ml");
const runCheck = document.getElementById("run-check");
const results = document.getElementById("results");
const unslopPanel = document.getElementById("unslop-panel");
const unslopResults = document.getElementById("unslop-results");

let selectedFile = null;
let adapters = [];
let lastCheck = null;
let lastHtml = "";
let lastUnslop = null;
let signalFilter = null;
const scrollBehavior = window.matchMedia("(prefers-reduced-motion: reduce)").matches
  ? "auto"
  : "smooth";

dropzone(drop, async (file) => {
  if (!/\.(txt|md)$/i.test(file.name)) {
    clearFile();
    toast("tell accepts .txt and .md files");
    return;
  }
  try {
    const content = await file.text();
    selectedFile = file;
    draft.value = content;
    sourceNote.textContent = file.name;
    updateCount();
    invalidateResults();
  } catch {
    clearFile();
    toast("couldn't read that file as text");
  }
});

draft.addEventListener("input", () => {
  if (selectedFile) clearFile(false);
  updateCount();
  invalidateResults();
});
document.getElementById("clear-file").addEventListener("click", () => clearFile());
offline.addEventListener("change", updateEgressWarning);

runCheck.addEventListener("click", async () => {
  if (!draft.value.trim()) {
    toast("paste a draft or choose a .txt / .md file first");
    draft.focus();
    return;
  }
  updateEgressWarning();
  runCheck.disabled = true;
  try {
    await withBusy(results.parentElement, "running local signals and eligible checkers…", async () => {
      const form = inputForm();
      form.append("offline", String(offline.checked));
      if (!offline.checked) {
        const intent = await api("/api/tell/egress-intent", { body: inputForm() });
        if (intent.adapters.length) {
          const names = intent.adapters.map((adapter) => adapter.display_name).join(", ");
          const confirmed = window.confirm(
            `Send this draft to ${names}? The text will leave this machine for this check only.`,
          );
          if (!confirmed) return;
          form.append("egress_token", intent.token);
        }
      }
      form.append("ml", String(ml.checked));
      const payload = await api("/api/tell/check?output=html", { body: form });
      lastCheck = payload;
      lastHtml = payload.html;
      renderCheck(payload);
      results.hidden = false;
      unslopPanel.hidden = false;
      results.scrollIntoView({ behavior: scrollBehavior, block: "start" });
    });
  } catch (err) {
    toast(err.message);
  } finally {
    runCheck.disabled = false;
  }
});

document.getElementById("run-unslop").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  const maxIterations = document.getElementById("max-iterations").value;
  button.disabled = true;
  try {
    await withBusy(unslopPanel, "applying deterministic transforms…", async () => {
      const form = inputForm();
      form.append("max_iterations", maxIterations);
      const payload = await api("/api/tell/unslop", { body: form });
      lastUnslop = payload;
      renderUnslop(payload);
      unslopResults.hidden = false;
      unslopResults.scrollIntoView({ behavior: scrollBehavior, block: "start" });
    });
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("download-html").addEventListener("click", () => {
  if (lastHtml) downloadText("tell-report.html", lastHtml);
});

document.getElementById("copy-clean").addEventListener("click", async (event) => {
  if (!lastUnslop) return;
  try {
    await navigator.clipboard.writeText(lastUnslop.final);
    const button = event.currentTarget;
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy cleaned text"; }, 1500);
  } catch {
    toast("couldn't copy — select the cleaned text manually");
  }
});

document.getElementById("download-clean").addEventListener("click", () => {
  if (lastUnslop) downloadText(lastUnslop.file.filename, lastUnslop.final);
});

document.getElementById("signal-list").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-signal]");
  if (!button) return;
  signalFilter = signalFilter === button.dataset.signal ? null : button.dataset.signal;
  applySignalFilter();
});

function inputForm() {
  const form = new FormData();
  if (selectedFile) form.append("file", selectedFile);
  else form.append("text", draft.value);
  return form;
}

function clearFile(clearDraft = true) {
  selectedFile = null;
  drop.file = null;
  drop.querySelector("input").value = "";
  drop.parentElement.querySelector(".file-chip").hidden = true;
  sourceNote.textContent = "pasted text";
  if (clearDraft) draft.value = "";
  updateCount();
  invalidateResults();
}

function updateCount() {
  const count = draft.value.length;
  charCount.textContent = `${count.toLocaleString()} character${count === 1 ? "" : "s"}`;
}

function invalidateResults() {
  lastCheck = null;
  lastHtml = "";
  lastUnslop = null;
  results.hidden = true;
  unslopPanel.hidden = true;
  unslopResults.hidden = true;
}

async function loadAdapters() {
  try {
    const payload = await api("/api/tell/adapters", { method: "GET" });
    adapters = payload.adapters;
    adapterLine.innerHTML = [
      "<strong>remote keys</strong>",
      ...adapters.map((adapter) => (
        `<span class="${adapter.keyed ? "adapter-keyed" : "adapter-idle"}">` +
        `${adapter.keyed ? "●" : "○"} ${esc(adapter.display_name)}</span>`
      )),
      `<span>${payload.ml_available ? "local ML ready" : "local ML extra not installed"}</span>`,
    ].join("");
    updateEgressWarning();
  } catch (err) {
    adapterLine.textContent = "adapter status unavailable";
    toast(err.message);
  }
}

function updateEgressWarning() {
  const keyed = adapters.filter((adapter) => adapter.keyed);
  if (!keyed.length || offline.checked) {
    egressWarning.hidden = true;
    return;
  }
  egressWarning.textContent =
    `remote mode is armed for ${keyed.map((item) => item.display_name).join(", ")}; ` +
    "the app will ask before every send";
  egressWarning.hidden = false;
}

function renderCheck(payload) {
  document.getElementById("checker-table").innerHTML = renderTable(
    payload.detectors,
    [
      { key: "display_name", label: "checker" },
      {
        key: "status",
        label: "status",
        render: (value) => `<span class="badge ${statusBadge(value)}">${esc(value)}</span>`,
      },
      {
        key: "ai_probability",
        label: "AI probability",
        render: (value) => {
          if (value == null) return "—";
          const pct = Math.max(0, Math.min(100, value * 100));
          return `<span class="checker-bar" aria-hidden="true"><span style="width:${pct}%"></span></span>${pct.toFixed(1)}%`;
        },
      },
      { key: "label", label: "vendor label", render: (value) => esc(value || "—") },
      { key: "detail", label: "detail", render: (value) => esc(value || "—") },
    ],
  );
  payload.detectors.forEach((detector, index) => {
    document.querySelector(`#checker-table tbody tr:nth-child(${index + 1})`)
      ?.classList.add(`row-${detector.status}`);
  });

  const signalList = document.getElementById("signal-list");
  signalList.innerHTML = payload.signals.map((signal) => `
    <button class="signal-card severity-${esc(signal.severity)}" type="button"
            data-signal="${esc(signal.signal)}" aria-pressed="false">
      <span class="signal-head">
        <strong>${esc(signal.title)}</strong>
        <span class="badge ${severityBadge(signal.severity)}">${esc(signal.severity)}</span>
      </span>
      <p>${esc(signal.summary)} · density ${Number(signal.score).toFixed(2)}</p>
    </button>
  `).join("");

  const spans = payload.signals.flatMap((signal) => signal.evidence.map((item) => ({
    start: item.start,
    end: item.end,
    name: signal.signal,
  })));
  document.getElementById("source-view").innerHTML = spanMarkup(
    draft.value,
    spans,
    "signal",
  );
  signalFilter = null;
  applySignalFilter();
}

// Server offsets are the source of truth. Split only at span boundaries, then
// merge overlapping labels into one mark so no client-side signal parser sneaks in.
function spanMarkup(text, spans, attribute) {
  const usable = spans
    .filter((span) => Number.isInteger(span.start) && Number.isInteger(span.end))
    .filter((span) => span.start >= 0 && span.end > span.start && span.end <= text.length);
  const points = new Set([0, text.length]);
  usable.forEach((span) => {
    points.add(span.start);
    points.add(span.end);
  });
  const sorted = [...points].sort((a, b) => a - b);
  const pieces = [];
  for (let index = 0; index < sorted.length - 1; index += 1) {
    const start = sorted[index];
    const end = sorted[index + 1];
    if (end <= start) continue;
    const names = [...new Set(
      usable
        .filter((span) => span.start < end && start < span.end)
        .map((span) => span.name),
    )];
    const content = esc(text.slice(start, end));
    pieces.push(names.length
      ? `<mark data-${attribute}="${esc(names.join(" "))}">${content}</mark>`
      : content);
  }
  return pieces.join("");
}

function applySignalFilter() {
  document.querySelectorAll(".signal-card").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.signal === signalFilter));
  });
  document.querySelectorAll("mark[data-signal]").forEach((mark) => {
    const names = mark.dataset.signal.split(" ");
    mark.classList.toggle("muted-mark", Boolean(signalFilter && !names.includes(signalFilter)));
  });
}

function renderUnslop(payload) {
  let before = new Map((lastCheck?.signals || []).map((signal) => [signal.signal, signal]));
  const rows = payload.iterations.map((iteration) => {
    const changes = iteration.report.signals
      .filter((signal) => before.get(signal.signal)?.severity !== signal.severity)
      .map((signal) => {
        const previous = before.get(signal.signal)?.severity || "—";
        return `<span class="change">${esc(signal.title)}: ` +
          `${severityChip(previous)} → ${severityChip(signal.severity)}</span>`;
      });
    before = new Map(iteration.report.signals.map((signal) => [signal.signal, signal]));
    return {
      iteration: iteration.index,
      edits: iteration.edits.length,
      changes: changes.length ? changes.join("") : "no severity changes",
    };
  });
  document.getElementById("iteration-table").innerHTML = rows.length
    ? renderTable(rows, [
        { key: "iteration", label: "iteration", className: "num" },
        { key: "edits", label: "edits", className: "num" },
        { key: "changes", label: "severity changes", render: (value) => value },
      ])
    : '<p class="empty">already stable — no deterministic edits were needed.</p>';

  document.getElementById("word-diff").innerHTML = payload.diff.map((operation) => {
    const text = esc(operation.text);
    if (operation.op === "insert") return `<ins>${text}</ins>`;
    if (operation.op === "delete") return `<del>${text}</del>`;
    return text;
  }).join("");

  const suggestionSpans = payload.suggestions.map((item) => ({
    start: item.start,
    end: item.end,
    name: item.pattern,
  }));
  document.getElementById("clean-text").innerHTML = spanMarkup(
    payload.final,
    suggestionSpans,
    "suggestion",
  );
  document.getElementById("suggestions").innerHTML = payload.suggestions.length
    ? `<ol class="suggestion-list">${payload.suggestions.map((item) => `
        <li><strong>${esc(item.pattern.replaceAll("_", " "))}</strong>: ${esc(item.advice)}
          <small>${esc(item.excerpt)}</small>
        </li>
      `).join("")}</ol>`
    : '<p class="empty">no judgment-only patterns were flagged.</p>';
}

function statusBadge(status) {
  return { ran: "badge-ok", skipped: "badge-type", error: "badge-pii" }[status] || "badge-type";
}

function severityBadge(severity) {
  return { info: "badge-type", notice: "badge-warn", strong: "badge-pii" }[severity] || "badge-type";
}

function severityChip(severity) {
  if (severity === "—") return "—";
  return `<span class="badge ${severityBadge(severity)}">${esc(severity)}</span>`;
}

updateCount();
loadAdapters();
