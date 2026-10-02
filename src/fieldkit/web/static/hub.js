// Dim tools that aren't installed, and block cards whose package changed
// under a running hub. Static previews keep every card live.
try {
  const res = await fetch("/api/plugins");
  if (res.ok) {
    const payload = await res.json();
    const plugins = payload.plugins || [];
    const byName = new Map(plugins.map((plugin) => [plugin.name, plugin]));
    const banner = document.getElementById("restart-banner");
    if (banner && payload.restart_required) banner.hidden = false;
    for (const card of document.querySelectorAll(".kit-card[data-tool]")) {
      const tool = card.dataset.tool;
      const row = byName.get(tool);
      const ready = row && row.status === "installed" && row.runtime === "ready";
      if (ready) continue;
      card.classList.add("kit-card--off");
      card.removeAttribute("href");
      card.setAttribute("aria-disabled", "true");
      card.querySelector(".arrow")?.remove();
      const hint = card.querySelector(".kit-add");
      if (hint) {
        hint.hidden = false;
        if (row && row.runtime === "restart") {
          hint.textContent = "restart fieldkit serve";
        }
      }
    }
  }
} catch {
  // No server means there is nothing useful to dim.
}
