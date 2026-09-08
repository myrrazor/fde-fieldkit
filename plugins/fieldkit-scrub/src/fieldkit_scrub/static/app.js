import { api, dropzone, esc, renderTable, downloadB64, downloadText, toast, withBusy } from "/fieldkit.js";

const KINDS = ["email", "phone", "ssn", "credit_card", "ip", "name", "secret"];

const drop = document.getElementById("drop");
const result = document.getElementById("result");
const go = document.getElementById("go");
const mapping = document.getElementById("mapping");
const mappingWarn = document.getElementById("mapping-warn");
const chip = drop.parentElement.querySelector(".file-chip");

document.getElementById("kinds").innerHTML = KINDS.map(
  (k) => `<label class="check-pill"><input type="checkbox" value="${k}" checked> ${k.replace("_", " ")}</label>`
).join("");

dropzone(drop, () => { go.disabled = false; result.innerHTML = ""; });
chip.querySelector("button").addEventListener("click", () => {
  chip.hidden = true;
  drop.file = null;
  go.disabled = true;
  result.innerHTML = "";
});
mapping.addEventListener("change", () => { mappingWarn.hidden = !mapping.checked; });
go.addEventListener("click", scrub);

function selectedKinds() {
  return [...document.querySelectorAll("#kinds input:checked")].map((el) => el.value);
}

async function scrub() {
  const file = drop.file;
  if (!file) return;
  const kinds = selectedKinds();
  if (!kinds.length) return toast("pick at least one kind to scrub");

  result.innerHTML = "";
  try {
    await withBusy(result, `scrubbing ${file.name}…`, async () => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("kinds", kinds.join(","));
      fd.append("include_mapping", mapping.checked ? "true" : "false");
      const r = await api("/api/scrub", { body: fd });
      await render(r, file);
    });
  } catch (err) {
    toast(err.message);
  }
}

async function render(r, file) {
  const stats = Object.entries(r.summary.replaced)
    .map(([k, n]) => `<div class="stat"><div class="n">${n.toLocaleString()}</div><div class="k">${esc(k.replace("_", " "))}</div></div>`)
    .join("");

  const byColumn = Object.entries(r.summary.by_column).flatMap(([col, kinds]) =>
    Object.entries(kinds).map(([kind, n]) => ({ col, kind, n }))
  );
  const byColumnTable = byColumn.length
    ? `<p class="label-eng">by column</p>` +
      renderTable(byColumn, [
        { key: "col", label: "column", className: "mono" },
        { key: "kind", label: "kind", render: (v) => `<span class="badge badge-pii">${esc(v)}</span>` },
        { key: "n", label: "values replaced", className: "num" },
      ])
    : "";

  const preview = await beforeAfterPreview(r, file);

  result.innerHTML = `
    <div class="report">
      <div class="report-head">
        <span class="title">${esc(r.file.filename)}</span>
        <div class="actions">
          ${r.mapping ? '<button class="btn btn-ghost" id="dl-map">Download mapping</button>' : ""}
          <button class="btn btn-primary" id="dl-file">Download scrubbed file</button>
        </div>
      </div>
      <div class="report-body">
        ${Object.keys(r.summary.replaced).length
          ? `<div class="stat-row">${stats}</div>`
          : '<p class="empty">nothing matched the selected kinds — the file is unchanged.</p>'}
        ${byColumnTable}
        ${preview}
      </div>
    </div>`;

  document.getElementById("dl-file").addEventListener("click", () => downloadB64(r.file));
  if (r.mapping) {
    document.getElementById("dl-map").addEventListener("click", () => {
      downloadText(`${file.name}.mapping.json`, JSON.stringify(r.mapping, null, 2));
    });
  }
}

// small quoted-field csv parser — preview only, server output is well-formed
function parseCsv(text, delim) {
  const rows = [];
  let row = [], cur = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"') {
        if (text[i + 1] === '"') { cur += '"'; i++; } else quoted = false;
      } else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === delim) { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; }
    else if (c !== "\r") cur += c;
  }
  if (cur !== "" || row.length) { row.push(cur); rows.push(row); }
  return rows.filter((cells) => cells.length > 1 || cells[0] !== "");
}

async function beforeAfterPreview(r, file) {
  const ext = file.name.toLowerCase().split(".").pop();
  if (!["csv", "tsv"].includes(ext)) return "";
  const delim = ext === "tsv" ? "\t" : ",";

  const before = parseCsv(await file.text(), delim);
  const after = parseCsv(atob(r.file.content_b64), delim);
  if (before.length < 2 || after.length < 2) return "";

  const cols = Math.min(before[0].length, 8);
  const rows = Math.min(before.length - 1, 6, after.length - 1);
  const table = (grid, compare) => {
    const head = grid[0].slice(0, cols).map((h) => `<th>${esc(h)}</th>`).join("");
    const body = Array.from({ length: rows }, (_, i) => {
      const cells = grid[i + 1].slice(0, cols).map((v, j) => {
        const changed = compare && compare[i + 1] && compare[i + 1][j] !== v;
        return `<td class="mono${changed ? " cell-changed" : ""}">${esc(v)}</td>`;
      }).join("");
      return `<tr>${cells}</tr>`;
    }).join("");
    return `<div class="tablewrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  };

  return `
    <p class="label-eng">before</p>${table(before, null)}
    <p class="label-eng">after — changed cells highlighted</p>${table(after, before)}
    <p class="empty">first ${rows} rows · first ${cols} columns</p>`;
}
