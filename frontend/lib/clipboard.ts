/** Copy text to the clipboard, including over plain HTTP.
 *
 * The Clipboard API only exists in a secure context, and a self-hosted box is
 * usually reached at http://<lan-ip>:3000 — where `navigator.clipboard` is
 * undefined. Falling back to the legacy selection copy keeps the button working
 * there instead of failing silently. */
export async function copyText(text: string): Promise<boolean> {
  if (!text) return false;
  try {
    if (window.isSecureContext && navigator.clipboard) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* denied or unavailable — try the legacy path below */
  }
  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    // off-screen but focusable, and fixed so selecting it never scrolls the page
    area.style.position = "fixed";
    area.style.top = "0";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(area);
    return ok;
  } catch {
    return false;
  }
}
