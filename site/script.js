const toolLinks = [...document.querySelectorAll("[data-tool-link]")];

function syncToolState() {
  const selected = window.location.hash || "#tool-xray";

  for (const link of toolLinks) {
    const isSelected = link.hash === selected;
    link.setAttribute("aria-expanded", String(isSelected));
    if (isSelected) {
      link.setAttribute("aria-current", "true");
    } else {
      link.removeAttribute("aria-current");
    }
  }
}

async function writeClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Browser automation and locked-down customer machines may deny this API.
      // The selection fallback below still works without a permission prompt.
    }
  }

  const input = document.createElement("textarea");
  input.value = text;
  input.setAttribute("readonly", "");
  input.style.position = "fixed";
  input.style.opacity = "0";
  document.body.append(input);
  input.select();

  const copied = document.execCommand("copy");
  input.remove();

  if (!copied) {
    throw new Error("copy failed");
  }
}

for (const button of document.querySelectorAll("[data-copy-target]")) {
  button.addEventListener("click", async () => {
    const target = document.getElementById(button.dataset.copyTarget);
    const status = button.parentElement.querySelector(".copy-status");

    try {
      await writeClipboard(target.textContent.trim());
      button.textContent = "Copied";
      status.textContent = "Command copied to clipboard.";
    } catch {
      button.textContent = "Select";
      status.textContent = "Clipboard access failed. Select the command manually.";
    }

    window.setTimeout(() => {
      button.textContent = "Copy";
    }, 1800);
  });
}

window.addEventListener("hashchange", syncToolState);
syncToolState();
