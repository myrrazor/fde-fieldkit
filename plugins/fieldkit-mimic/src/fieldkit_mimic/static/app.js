import { api, dropzone, esc, renderTable, downloadB64, toast, withBusy } from "/fieldkit.js";

const drop = document.getElementById("drop");
const result = document.getElementById("result");
const specSection = document.getElementById("spec-section");
const spec = document.getElementById("spec");
const chip = drop.parentElement.querySelector(".file-chip");

dropzone(drop, learn);
chip.querySelector("button").addEventListener("click", () => {
  chip.hidden = true;
  drop.file = null;
  specSection.hidden = true;
  result.innerHTML = "";
});
document.getElementById("go").addEventListener("click", generate);

async function learn(file) {
  result.innerHTML = "";
  try {
    await withBusy(result, `learning from ${file.name}…`, async () => {
      const fd = new FormData();
      fd.append("file", file);
      const r = await api("/api/mimic/learn", { body: fd });
      spec.value = r.spec_yaml;
      specSection.hidden = false;
    });
  } catch (err) {
    toast(err.message);
  }
}

async function generate() {
  const n = Number(document.getElementById("n").value);
  const seed = Number(document.getElementById("seed").value) || 0;
  const fmt = document.getElementById("fmt").value;
  if (!Number.isInteger(n) || n < 1 || n > 100000) {
    return toast("rows must be a whole number between 1 and 100,000");
  }
  if (!spec.value.trim()) return toast("the spec is empty — drop a sample file first");

  result.innerHTML = "";
  try {
    await withBusy(result, `generating ${n.toLocaleString()} rows…`, async () => {
      const fd = new FormData();
      fd.append("spec_yaml", spec.value);
      fd.append("n", String(n));
      fd.append("seed", String(seed));
      fd.append("fmt", fmt);
      const r = await api("/api/mimic/generate", { body: fd });
      render(r, n, seed, fmt);
    });
  } catch (err) {
    toast(err.message);
  }
}

function render(r, n, seed, fmt) {
  const previewTable = r.preview.length
    ? renderTable(
        r.preview,
        Object.keys(r.preview[0]).map((key) => ({ key, label: key, className: "mono" }))
      )
    : '<p class="empty">no rows generated.</p>';

  result.innerHTML = `
    <div class="report">
      <div class="report-head">
        <span class="title">${esc(r.file.filename)}</span>
        <div class="actions">
          <button class="btn btn-primary" id="dl-file">Download file</button>
        </div>
      </div>
      <div class="report-body">
        <div class="stat-row">
          <div class="stat"><div class="n">${n.toLocaleString()}</div><div class="k">rows generated</div></div>
          <div class="stat"><div class="n">${seed}</div><div class="k">seed</div></div>
          <div class="stat"><div class="n">${esc(fmt)}</div><div class="k">format</div></div>
        </div>
        <p class="label-eng" style="margin-top:18px">preview</p>
        ${previewTable}
        <p class="empty">first ${Math.min(r.preview.length, 20)} rows — same seed always gives the same file</p>
      </div>
    </div>`;

  document.getElementById("dl-file").addEventListener("click", () => downloadB64(r.file));
}
