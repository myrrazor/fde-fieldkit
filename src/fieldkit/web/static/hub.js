// Dim tools that aren't installed. Static previews keep every card live.
try {
  const res = await fetch("/api/plugins");
  if (res.ok) {
    const { plugins } = await res.json();
    const installed = new Set(plugins.filter((p) => p.status === "installed").map((p) => p.name));
    for (const card of document.querySelectorAll(".kit-card[data-tool]")) {
      const tool = card.dataset.tool;
      if (installed.has(tool)) continue;
      card.classList.add("kit-card--off");
      card.removeAttribute("href");
      card.setAttribute("aria-disabled", "true");
      card.querySelector(".arrow")?.remove();
      card.querySelector(".kit-add")?.removeAttribute("hidden");
    }
  }
} catch {
  // No server means there is nothing useful to dim.
}
