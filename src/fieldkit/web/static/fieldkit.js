// shared helpers for the fieldkit tool pages. no framework, no build step.

export function esc(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

export async function api(url, { method = "POST", body, headers } = {}) {
  let res;
  try {
    res = await fetch(url, { method, body, headers });
  } catch {
    throw new Error("can't reach the local server — is `fieldkit serve` still running?");
  }
  if (!res.ok) {
    let msg = `request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.error) msg = data.error;
      else if (data.detail) msg = typeof data.detail === "string" ? data.detail : msg;
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

// busy indicator inside a container while an async task runs
export async function withBusy(container, label, task) {
  const busy = document.createElement("p");
  busy.className = "busy";
  busy.innerHTML = `<span class="spinner" aria-hidden="true"></span>${esc(label)}`;
  container.append(busy);
  const stopIndicator = startThinkingOrb(busy.querySelector(".spinner"));
  try {
    return await task();
  } finally {
    stopIndicator();
    busy.remove();
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
