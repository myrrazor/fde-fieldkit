import { api, dropzone, esc, renderTable, toast, withBusy } from "/fieldkit.js";

const result = document.getElementById("result");
const modes = {
  check: document.getElementById("mode-check"),
  diff: document.getElementById("mode-diff"),
  eval: document.getElementById("mode-eval"),
};
const panes = {
  check: document.getElementById("pane-check"),
  diff: document.getElementById("pane-diff"),
  eval: document.getElementById("pane-eval"),
};

const dropCheck = document.getElementById("drop-check");
const dropBefore = document.getElementById("drop-before");
const dropAfter = document.getElementById("drop-after");
const dropEvalSpec = document.getElementById("drop-eval-spec");
const dropEvalSuite = document.getElementById("drop-eval-suite");
const goDiff = document.getElementById("go-diff");
const goEval = document.getElementById("go-eval");

function wireChip(el) {
  const chip = el.parentElement.querySelector(".file-chip");
  chip?.querySelector("button")?.addEventListener("click", () => {
    chip.hidden = true;
    el.file = null;
    result.innerHTML = "";
    refresh();
  });
}

function refresh() {
  goDiff.disabled = !(dropBefore.file && dropAfter.file);
  goEval.disabled = !(dropEvalSpec.file && dropEvalSuite.file);
}

dropzone(dropCheck, (file) => check(file));
dropzone(dropBefore, refresh);
dropzone(dropAfter, refresh);
dropzone(dropEvalSpec, refresh);
dropzone(dropEvalSuite, refresh);
for (const el of [dropCheck, dropBefore, dropAfter, dropEvalSpec, dropEvalSuite]) {
  wireChip(el);
}

for (const [name, button] of Object.entries(modes)) {
  button.addEventListener("click", () => {
    for (const [key, pane] of Object.entries(panes)) {
      pane.hidden = key !== name;
      modes[key].setAttribute("aria-pressed", key === name ? "true" : "false");
    }
    result.innerHTML = "";
  });
}

goDiff.addEventListener("click", diff);
goEval.addEventListener("click", score);

async function check(file) {
  result.innerHTML = "";
  try {
    await withBusy(result, `checking ${file.name}…`, async () => {
      const fd = new FormData();
      fd.append("file", file);
      renderCheck(await api("/api/awcp", { body: fd }));
    });
  } catch (err) {
    toast(err.message);
  }
}

async function diff() {
  result.innerHTML = "";
  try {
    await withBusy(result, "comparing specs…", async () => {
      const fd = new FormData();
      fd.append("file_a", dropBefore.file);
      fd.append("file_b", dropAfter.file);
      renderDiff(await api("/api/awcp/diff", { body: fd }));
    });
  } catch (err) {
    toast(err.message);
  }
}

async function score() {
  result.innerHTML = "";
  try {
    await withBusy(result, "scoring recorded cases…", async () => {
      const fd = new FormData();
      fd.append("file", dropEvalSpec.file);
      fd.append("suite", dropEvalSuite.file);
      renderEval(await api("/api/awcp/eval", { body: fd }));
    });
  } catch (err) {
    toast(err.message);
  }
}

function renderCheck(r) {
  const stats = [
    `<div class="stat"><div class="n">${r.ok ? "ok" : "fail"}</div><div class="k">status</div></div>`,
    `<div class="stat"><div class="n">${esc(r.workload_name || "—")}</div><div class="k">workload</div></div>`,
    `<div class="stat"><div class="n">${r.tools.length}</div><div class="k">tools</div></div>`,
    `<div class="stat"><div class="n">${(r.fingerprint.prompt_hashes && Object.keys(r.fingerprint.prompt_hashes).length) || 0}</div><div class="k">prompts</div></div>`,
  ].join("");
  const errors = (r.errors || []).length
    ? `<p class="note-warn">${r.errors.map(esc).join("<br>")}</p>`
    : "";
  const warnings = (r.warnings || []).length
    ? `<p class="note-warn">${r.warnings.map(esc).join("<br>")}</p>`
    : "";
  const toolRows = r.tools.map((tool) => ({
    name: tool.name,
    approval: tool.requires_approval ? "required" : "none",
    risk: (tool.risk_tokens || []).join(", ") || "—",
  }));
  const tools = toolRows.length
    ? renderTable(toolRows, [
        { key: "name", label: "tool", className: "mono" },
        { key: "approval", label: "approval" },
        { key: "risk", label: "risk" },
      ])
    : '<p class="empty">no allowed tools declared.</p>';
  result.innerHTML = `
    <div class="stat-row">${stats}</div>
    ${errors}${warnings}
    <p class="muted"><code>${esc(r.fingerprint.config_hash)}</code></p>
    ${tools}
    <p class="note">Local check only. Nothing left this machine.</p>
  `;
}

function renderDiff(r) {
  const rows = r.changes.map((change) => ({
    kind: change.category,
    path: change.path,
    before: stringify(change.before),
    after: stringify(change.after),
  }));
  result.innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="n">${r.changes.length}</div><div class="k">changes</div></div>
    </div>
    ${
      rows.length
        ? renderTable(rows, [
            { key: "kind", label: "kind" },
            { key: "path", label: "path", className: "mono" },
            { key: "before", label: "before", className: "mono" },
            { key: "after", label: "after", className: "mono" },
          ])
        : '<p class="empty">no changes.</p>'
    }
  `;
}

function renderEval(r) {
  const rows = (r.results || []).map((item) => ({
    id: item.case_id,
    score: Number(item.score).toFixed(2),
    passed: item.passed ? "yes" : "no",
    reason: item.reason,
  }));
  result.innerHTML = `
    <div class="stat-row">
      <div class="stat"><div class="n">${esc(r.status)}</div><div class="k">status</div></div>
      <div class="stat"><div class="n">${Number(r.score).toFixed(2)}</div><div class="k">score</div></div>
      <div class="stat"><div class="n">${r.metrics?.case_count ?? rows.length}</div><div class="k">cases</div></div>
    </div>
    ${renderTable(rows, [
      { key: "id", label: "case", className: "mono" },
      { key: "score", label: "score", className: "num" },
      { key: "passed", label: "pass" },
      { key: "reason", label: "reason" },
    ])}
    <p class="note">Scored from recorded cases. No model ran.</p>
  `;
}

function stringify(value) {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}
