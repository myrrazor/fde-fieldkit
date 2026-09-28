// shared helpers for the fieldkit tool pages. no framework, no build step.

export function esc(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

export async function api(url, { method = "POST", body, headers, signal } = {}) {
  let res;
  try {
    res = await fetch(url, { method, body, headers, signal });
  } catch (err) {
    if (err && err.name === "AbortError") throw err;
    throw new Error("can't reach the local server — is `fieldkit serve` still running?");
  }
  if (!res.ok) {
    let msg = `request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.error) msg = data.error;
      else if (data.detail) msg = formatDetail(data.detail) || msg;
    } catch { /* body wasn't json, keep the status message */ }
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// wire a .drop element to a hidden file input + drag/drop. onFile(file) fires
// on every selection; we keep the chosen file on the element for later reads.
export function dropzone(el, onFile) {
  const input = el.querySelector("input[type=file]");
  const pick = (file) => {
    if (!file) return;
    el.file = file;
    const chip = el.parentElement.querySelector(".file-chip");
    if (chip) {
      chip.hidden = false;
      chip.querySelector("span").textContent = `${file.name} · ${fmtBytes(file.size)}`;
    }
    onFile(file);
  };
  el.addEventListener("click", () => input.click());
  el.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); input.click(); }
  });
  input.addEventListener("change", () => pick(input.files[0]));
  el.addEventListener("dragover", (e) => { e.preventDefault(); el.classList.add("dragover"); });
  el.addEventListener("dragleave", () => el.classList.remove("dragover"));
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    el.classList.remove("dragover");
    pick(e.dataTransfer.files[0]);
  });
}

function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (!Array.isArray(detail)) return "";
  return detail
    .map((item) => {
      if (typeof item === "string") return item;
      const loc = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== "body" && part !== "query").join(".")
        : "";
      const text = item.msg || item.message || "invalid";
      return loc ? `${loc}: ${text}` : text;
    })
    .filter(Boolean)
    .join("; ");
}

// Drop the previous in-flight request when the user picks another file.
export function latestRequest() {
  let controller = null;
  let generation = 0;
  return {
    start() {
      if (controller) controller.abort();
      controller = new AbortController();
      const token = ++generation;
      const signal = controller.signal;
      return { signal, current: () => token === generation && !signal.aborted };
    },
    invalidate() {
      if (controller) controller.abort();
      controller = null;
      generation += 1;
    },
  };
}

export function fmtBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// render [{...}, ...] rows into a dense table. columns: [{key, label, className?, render?}]
export function renderTable(rows, columns) {
  const head = columns
    .map((c) => `<th class="${c.className || ""}">${esc(c.label)}</th>`)
    .join("");
  const body = rows
    .map((row) => {
      const cells = columns
        .map((c) => {
          const raw = row[c.key];
          const html = c.render ? c.render(raw, row) : esc(raw ?? "");
          return `<td class="${c.className || ""}">${html}</td>`;
        })
        .join("");
      return `<tr>${cells}</tr>`;
    })
    .join("");
  return `<div class="tablewrap"><table class="data"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

export function downloadB64(file) {
  const bytes = Uint8Array.from(atob(file.content_b64), (c) => c.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([bytes]));
  const a = document.createElement("a");
  a.href = url;
  a.download = file.filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function downloadText(filename, text) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

let toastTimer;
export function toast(message) {
  document.querySelector(".toast")?.remove();
  const el = document.createElement("div");
  el.className = "toast";
  el.role = "alert";
  el.textContent = message;
  document.body.append(el);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.remove(), 6000);
}

// Two heavy jobs run at once; anything past that is waiting on the hub.
// Each tab records only its own key so two pages cannot overwrite each other.
const BUSY_PREFIX = "fieldkit-busy:";
const BUSY_SLOTS = 2;

function snapshotBusy(now) {
  const rows = [];
  try {
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key || !key.startsWith(BUSY_PREFIX)) continue;
      let row;
      try {
        row = JSON.parse(localStorage.getItem(key) || "");
      } catch {
        continue;
      }
      if (!row || typeof row.started !== "number" || now - row.beat > 2000) continue;
      rows.push({ id: key, started: row.started });
    }
  } catch {
    return [];
  }
  rows.sort((a, b) => a.started - b.started || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  return rows;
}

// busy indicator inside a container while an async task runs
export async function withBusy(container, label, task) {
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  const key = BUSY_PREFIX + id;
  const started = Date.now();
  const busy = document.createElement("p");
  busy.className = "busy";
  const spinner = document.createElement("span");
  spinner.className = "spinner";
  spinner.setAttribute("aria-hidden", "true");
  const text = document.createElement("span");
  busy.append(spinner, text);

  const render = () => {
    const rows = snapshotBusy(Date.now());
    const index = rows.findIndex((row) => row.id === key);
    text.textContent = index >= BUSY_SLOTS ? "waiting for another job…" : label;
  };
  const beat = () => {
    try {
      localStorage.setItem(key, JSON.stringify({ started, beat: Date.now() }));
    } catch {
      text.textContent = label;
      return;
    }
    render();
  };
  beat();
  container.append(busy);
  const stopIndicator = startThinkingOrb(spinner);
  const timer = setInterval(beat, 400);
  window.addEventListener("storage", render);
  try {
    const value = await task();
    document.querySelector(".toast")?.remove();
    clearTimeout(toastTimer);
    return value;
  } finally {
    clearInterval(timer);
    window.removeEventListener("storage", render);
    stopIndicator();
    busy.remove();
    try {
      localStorage.removeItem(key);
    } catch { /* private mode or a torn-down page */ }
  }
}

function startThinkingOrb(host) {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return () => {};
  }

  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return () => {};

  const size = 20;
  const pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = size * pixelRatio;
  canvas.height = size * pixelRatio;
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;
  context.scale(pixelRatio, pixelRatio);
  host.classList.add("has-orb");
  host.append(canvas);

  const accent = getComputedStyle(document.documentElement)
    .getPropertyValue("--accent")
    .trim() || "#9a3412";
  // Motion geometry inspired by Jakub Antalik's MIT-licensed thinking-orbs package.
  const arcs = [
    { radius: 4.1, speed: 0.0021, phase: 0, length: 0.8 },
    { radius: 6.2, speed: -0.0017, phase: 2.1, length: 0.64 },
    { radius: 8.1, speed: 0.00125, phase: 4.2, length: 0.48 },
  ];
  let frame = null;
  let stopped = false;

  const draw = (time) => {
    context.clearRect(0, 0, size, size);
    context.strokeStyle = accent;
    context.lineCap = "round";
    context.lineWidth = 1.5;
    arcs.forEach((arc, index) => {
      const wobble = Math.sin(time * 0.0024 + arc.phase) * 0.45;
      const angle = time * arc.speed + arc.phase;
      context.globalAlpha = 0.56 + index * 0.2;
      context.beginPath();
      context.arc(
        size / 2,
        size / 2,
        arc.radius + wobble,
        angle,
        angle + Math.PI * arc.length,
      );
      context.stroke();
    });
    context.globalAlpha = 1;
    frame = requestAnimationFrame(draw);
  };

  const handleVisibility = () => {
    if (document.hidden && frame !== null) {
      cancelAnimationFrame(frame);
      frame = null;
    } else if (!document.hidden && !stopped && frame === null) {
      frame = requestAnimationFrame(draw);
    }
  };
  document.addEventListener("visibilitychange", handleVisibility);
  if (!document.hidden) frame = requestAnimationFrame(draw);

  return () => {
    stopped = true;
    if (frame !== null) cancelAnimationFrame(frame);
    document.removeEventListener("visibilitychange", handleVisibility);
    canvas.remove();
    host.classList.remove("has-orb");
  };
}
