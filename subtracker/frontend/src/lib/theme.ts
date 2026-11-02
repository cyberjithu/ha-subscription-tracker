/** Theme handling. "ha" follows Home Assistant (we run in a same-origin Ingress iframe), else the OS setting. */

type HaTheme = { dark: boolean; accent: string | null };

function readHaTheme(): HaTheme | null {
  try {
    const parent = window.parent;
    if (parent === window) return null;
    const style = parent.getComputedStyle(parent.document.documentElement);
    const bg = style.getPropertyValue("--primary-background-color").trim();
    const accent = style.getPropertyValue("--primary-color").trim() || null;
    if (!bg) return null;
    return { dark: isDark(bg), accent };
  } catch {
    return null; // cross-origin or not embedded
  }
}

function isDark(color: string): boolean {
  const probe = document.createElement("div");
  probe.style.color = color;
  document.body.appendChild(probe);
  const [r, g, b] = (getComputedStyle(probe).color.match(/\d+(\.\d+)?/g) ?? ["255", "255", "255"]).map(Number);
  probe.remove();
  return 0.2126 * r + 0.7152 * g + 0.0722 * b < 128;
}

const media = window.matchMedia("(prefers-color-scheme: dark)");

export function applyTheme(pref: string) {
  const root = document.documentElement;
  const ha = pref === "ha" ? readHaTheme() : null;
  const dark = pref === "dark" || (pref !== "light" && (ha ? ha.dark : media.matches));
  root.classList.toggle("dark", dark);
  root.style.colorScheme = dark ? "dark" : "light";
  if (ha?.accent) {
    root.style.setProperty("--primary", ha.accent);
    root.style.setProperty("--ring", ha.accent);
  } else {
    root.style.removeProperty("--primary");
    root.style.removeProperty("--ring");
  }
}

/** Re-apply when the OS scheme changes; returns an unsubscribe function. */
export function watchTheme(pref: string) {
  applyTheme(pref);
  const onChange = () => applyTheme(pref);
  media.addEventListener("change", onChange);
  return () => media.removeEventListener("change", onChange);
}
