import { api, dropzone, esc, renderTable, downloadText, toast, withBusy } from "/fieldkit.js";

const drop = document.getElementById("drop");
const result = document.getElementById("result");
const chip = drop.parentElement.querySelector(".file-chip");

dropzone(drop, profile);
chip.querySelector("button").addEventListener("click", () => {
  chip.hidden = true;
  drop.file = null;
  result.innerHTML = "";
});

async function profile(file) {
  result.innerHTML = "";
  try {
    await withBusy(result, `profiling ${file.name}…`, async () => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api("/api/xray", { body: fd });
      render(r, file);
    });
  } catch (err) {
    toast(err.message);
  }
}

const piiKinds = (pii) => Object.entries(pii).filter(([k]) => k !== "hit_rate");

function sig(v, digits = 4) {
  if (v == null || Number.isNaN(v)) return "—";
  return Number(Number(v).toPrecision(digits)).toLocaleString();
}

function render(r, file) {
  const piiCols = r.columns.filter((c) => piiKinds(c.pii).length > 0).length;

  const colRows = r.columns.map((c) => ({
    name: c.name,
    type: c.inferred_type,
    nulls: `${c.null_pct.toFixed(1)}%`,
    distinct: `${c.distinct_count} (${c.distinct_pct.toFixed(1)}%)`,
    top: c.top_values.length ? `${c.top_values[0][0]} (${c.top_values[0][1]})` : "",
    pii: c.pii,
  }));

  const columnsTable = renderTable(colRows, [
    { key: "name", label: "column", className: "mono" },
    { key: "type", label: "type", render: (v) => `<span class="badge badge-type">${esc(v)}</span>` },
    { key: "nulls", label: "nulls", className: "num" },
    { key: "distinct", label: "distinct", className: "num" },
    { key: "top", label: "top value", className: "mono" },
    {
      key: "pii",
      label: "pii",
      render: (pii) => {
        const kinds = piiKinds(pii);
        if (!kinds.length) return "—";
        return kinds
          .map(([k, conf]) => `<span class="badge badge-pii">${esc(k.toUpperCase())} ${Number(conf).toFixed(2)}</span>`)
          .join(" ");
      },
    },
  ]);

  const numericRows = r.columns
    .filter((c) => c.numeric)
    .map((c) => ({
      name: c.name,
      min: sig(c.numeric.min),
      p5: sig(c.numeric.p5),
      median: sig(c.numeric.median),
      mean: sig(c.numeric.mean),
      p95: sig(c.numeric.p95),
      max: sig(c.numeric.max),
      outliers: c.outlier_count,
    }));

  const numericTable = numericRows.length
    ? `<p class="label-eng">numeric detail</p>` +
      renderTable(numericRows, [
        { key: "name", label: "column", className: "mono" },
        { key: "min", label: "min", className: "num" },
        { key: "p5", label: "p5", className: "num" },
        { key: "median", label: "median", className: "num" },
        { key: "mean", label: "mean", className: "num" },
        { key: "p95", label: "p95", className: "num" },
        { key: "max", label: "max", className: "num" },
        { key: "outliers", label: "outliers", className: "num" },
      ])
    : "";

  const warnings = r.warnings.length
    ? `<p class="note-warn">${r.warnings.map(esc).join("<br>")}</p>`
    : "";

  result.innerHTML = `
    <div class="report">
      <div class="report-head">
        <span class="title">${esc(r.source)}</span>
        <div class="actions">
          <button class="btn btn-ghost" id="dl-json">Download JSON</button>
          <button class="btn btn-ghost" id="dl-html">Download HTML report</button>
        </div>
      </div>
      <div class="report-body">
        <div class="stat-row">
          <div class="stat"><div class="n">${r.row_count.toLocaleString()}</div><div class="k">rows</div></div>
          <div class="stat"><div class="n">${r.column_count}</div><div class="k">columns</div></div>
          <div class="stat"><div class="n">${esc(r.fmt)}</div><div class="k">format</div></div>
          <div class="stat"><div class="n">${piiCols}</div><div class="k">columns with PII</div></div>
        </div>
        ${warnings}
        <p class="label-eng" style="margin-top:18px">columns</p>
        ${columnsTable}
        ${numericTable}
      </div>
    </div>`;

  document.getElementById("dl-json").addEventListener("click", () => {
    downloadText(`profile-${file.name}.json`, JSON.stringify(r, null, 2));
  });
  document.getElementById("dl-html").addEventListener("click", async () => {
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { html } = await api("/api/xray?output=html", { body: fd });
      downloadText(`profile-${file.name}.html`, html);
    } catch (err) {
      toast(err.message);
    }
  });
}
