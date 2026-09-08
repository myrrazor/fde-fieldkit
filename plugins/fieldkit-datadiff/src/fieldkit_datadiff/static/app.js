import { api, dropzone, esc, renderTable, toast, withBusy } from "/fieldkit.js";

const dropA = document.getElementById("drop-a");
const dropB = document.getElementById("drop-b");
const keys = document.getElementById("keys");
const go = document.getElementById("go");
const result = document.getElementById("result");

for (const el of [dropA, dropB]) {
  dropzone(el, () => { go.disabled = !(dropA.file && dropB.file); });
  el.parentElement.querySelector(".file-chip button").addEventListener("click", (e) => {
    e.target.closest(".file-chip").hidden = true;
    el.file = null;
    go.disabled = true;
    result.innerHTML = "";
  });
}
go.addEventListener("click", diff);

async function diff() {
  result.innerHTML = "";
  try {
    await withBusy(result, "comparing…", async () => {
      const fd = new FormData();
      fd.append("file_a", dropA.file);
      fd.append("file_b", dropB.file);
      if (keys.value.trim()) fd.append("keys", keys.value.trim());
      const r = await api("/api/datadiff", { body: fd });
      render(r);
    });
  } catch (err) {
    toast(err.message);
  }
}

const sig = (v, d = 4) => Number(Number(v).toPrecision(d)).toLocaleString();

function render(r) {
  if (!keys.value.trim() && r.key_detection.candidates.length) {
    keys.placeholder = r.key_detection.candidates[0].join(",");
  }

  const stats = [
    `<div class="stat"><div class="n">${r.rows_a.toLocaleString()}</div><div class="k">rows before</div></div>`,
    `<div class="stat"><div class="n">${r.rows_b.toLocaleString()}</div><div class="k">rows after</div></div>`,
    r.rows
      ? `<div class="stat"><div class="n">+${r.rows.added}</div><div class="k">added</div></div>
         <div class="stat"><div class="n">−${r.rows.removed}</div><div class="k">removed</div></div>
         <div class="stat"><div class="n">~${r.rows.changed}</div><div class="k">changed</div></div>`
      : "",
  ].join("");

  const warnings = r.warnings.length
    ? `<p class="note-warn">${r.warnings.map(esc).join("<br>")}</p>`
    : "";

  const schemaRows = [
    ...r.schema.added_columns.map((c) => ({ kind: "added", badge: "badge-ok", col: c, detail: "new column" })),
    ...r.schema.removed_columns.map((c) => ({ kind: "removed", badge: "badge-pii", col: c, detail: "column dropped" })),
    ...r.schema.type_changes.map(([c, o, n]) => ({ kind: "type", badge: "badge-warn", col: c, detail: `${o} → ${n}` })),
    ...r.schema.nullability_changes.map(([c, o, n]) => ({
      kind: "nullability", badge: "badge-info", col: c, detail: `null % ${Number(o).toFixed(1)} → ${Number(n).toFixed(1)}`,
    })),
  ];
  const schemaTable = schemaRows.length
    ? renderTable(schemaRows, [
        { key: "kind", label: "change", render: (v, row) => `<span class="badge ${row.badge}">${esc(v)}</span>` },
        { key: "col", label: "column", className: "mono" },
        { key: "detail", label: "detail", className: "mono" },
      ])
    : '<p class="empty">no schema changes.</p>';

  let rowsSection;
  if (r.rows) {
    const auto = r.key_detection.auto ? ' <span class="badge badge-info">auto-detected</span>' : "";
    const changedCols = Object.entries(r.rows.changed_by_column).map(([col, n]) => ({ col, n }));
    const changedTable = changedCols.length
      ? renderTable(changedCols, [
          { key: "col", label: "column", className: "mono" },
          { key: "n", label: "cells changed", className: "num" },
        ])
      : '<p class="empty">no cell-level changes.</p>';
    const samples = r.rows.samples.changed.slice(0, 5);
    const samplesTable = samples.length
      ? `<p class="label-eng">sample changes</p>` +
        renderTable(samples, [
          { key: "key", label: "key", className: "mono", render: (v) => esc(Object.values(v).join(" · ")) },
          { key: "col", label: "column", className: "mono" },
          { key: "old", label: "old", className: "mono" },
          { key: "new", label: "new", className: "mono", render: (v) => `<span class="badge badge-warn">${esc(v)}</span>` },
        ])
      : "";
    rowsSection = `
      <p class="label-eng" style="margin-top:18px">rows · key: ${r.rows.key_columns.map(esc).join(", ")}${auto}</p>
      ${changedTable}
      ${samplesTable}`;
  } else {
    const candidates = r.key_detection.candidates.length
      ? ` Candidates: ${r.key_detection.candidates.map((c) => c.join(",")).map(esc).join(" · ")}`
      : "";
    rowsSection = `<p class="note-warn">No usable key — row-level diff skipped. Pick a key column above and diff again.${candidates}</p>`;
  }

  const driftRows = [
    ...Object.entries(r.drift.categorical).map(([col, d]) => ({
      col, kind: "categorical",
      detail: `new: ${d.new.length ? d.new.join(", ") : `${d.new_count} value(s)`} · ` +
        `vanished: ${d.vanished.length ? d.vanished.join(", ") : `${d.vanished_count} value(s)`}`,
    })),
    ...Object.entries(r.drift.numeric).map(([col, d]) => ({
      col, kind: "numeric",
      detail: `mean Δ ${d.mean_delta >= 0 ? "+" : ""}${sig(d.mean_delta)} (${d.mean_pct_change >= 0 ? "+" : ""}${Number(d.mean_pct_change).toFixed(1)}%)`,
    })),
  ];
  const driftTable = driftRows.length
    ? renderTable(driftRows, [
        { key: "col", label: "column", className: "mono" },
        { key: "kind", label: "kind", render: (v) => `<span class="badge badge-type">${esc(v)}</span>` },
        { key: "detail", label: "detail", className: "mono" },
      ])
    : '<p class="empty">no value drift in shared columns.</p>';

  result.innerHTML = `
    <div class="report">
      <div class="report-head">
        <span class="title">${esc(r.source_a)} → ${esc(r.source_b)}</span>
      </div>
      <div class="report-body">
        <div class="stat-row">${stats}</div>
        ${warnings}
        <p class="label-eng" style="margin-top:18px">schema</p>
        ${schemaTable}
        ${rowsSection}
        <p class="label-eng" style="margin-top:18px">drift</p>
        ${driftTable}
      </div>
    </div>`;
}
