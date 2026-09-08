import { api, esc, renderTable, downloadText, toast } from "/fieldkit.js";

const form = document.getElementById("add-form");
const text = document.getElementById("text");
const week = document.getElementById("week");
const entries = document.getElementById("entries");
const reportSection = document.getElementById("report-section");
const reportBody = document.getElementById("report-body");
const reportTitle = document.getElementById("report-title");

const TAG_BADGE = {
  win: "badge-ok",
  blocker: "badge-pii",
  decision: "badge-info",
  note: "badge-type",
  next: "badge-warn",
};

function isoWeek(d = new Date()) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const year = date.getUTCFullYear();
  const weekNo = Math.ceil(((date - Date.UTC(year, 0, 1)) / 86400000 + 1) / 7);
  return `${year}-W${String(weekNo).padStart(2, "0")}`;
}

week.value = isoWeek();
week.addEventListener("change", refresh);

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const tag = document.querySelector("#tags input:checked").value;
  try {
    await api("/api/debrief/entries", {
      body: JSON.stringify({ text: text.value, tag }),
      headers: { "Content-Type": "application/json" },
    });
    text.value = "";
    text.focus();
    refresh();
  } catch (err) {
    toast(err.message);
  }
});

entries.addEventListener("click", async (e) => {
  const btn = e.target.closest("button[data-id]");
  if (!btn) return;
  try {
    await api(`/api/debrief/entries/${btn.dataset.id}`, { method: "DELETE" });
    refresh();
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("copy-md").addEventListener("click", async (e) => {
  try {
    const { markdown } = await api(`/api/debrief/report?week=${week.value}&fmt=md`, { method: "GET" });
    await navigator.clipboard.writeText(markdown);
    const btn = e.target;
    const old = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => { btn.textContent = old; }, 1500);
  } catch (err) {
    toast(err.message);
  }
});

document.getElementById("dl-md").addEventListener("click", async () => {
  try {
    const { markdown } = await api(`/api/debrief/report?week=${week.value}&fmt=md`, { method: "GET" });
    downloadText(`status-${week.value}.md`, markdown);
  } catch (err) {
    toast(err.message);
  }
});

function fmtTs(ts) {
  const d = new Date(ts);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return `${hm} ${d.toLocaleDateString(undefined, { weekday: "short" })}`;
}

async function refresh() {
  try {
    const list = await api(`/api/debrief/entries?week=${week.value}`, { method: "GET" });
    entries.innerHTML = list.length
      ? renderTable(list, [
          { key: "ts", label: "when", className: "mono", render: (v) => esc(fmtTs(v)) },
          { key: "tag", label: "tag", render: (v) => `<span class="badge ${TAG_BADGE[v] || "badge-type"}">${esc(v)}</span>` },
          { key: "text", label: "entry" },
          {
            key: "id",
            label: "",
            render: (v) => `<button class="btn btn-danger" data-id="${v}" aria-label="delete entry ${v}">×</button>`,
          },
        ])
      : '<p class="empty">nothing logged this week yet — entries show up here as you add them.</p>';

    const { html } = await api(`/api/debrief/report?week=${week.value}&fmt=html`, { method: "GET" });
    reportBody.innerHTML = new DOMParser().parseFromString(html, "text/html").body.innerHTML;
    reportTitle.textContent = `weekly status · ${week.value}`;
    reportSection.hidden = false;
  } catch (err) {
    toast(err.message);
  }
}

refresh();
