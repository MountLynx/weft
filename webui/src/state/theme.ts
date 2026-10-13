/** 主题切换：沿用 weft-theme localStorage 键 + data-theme 属性（守卫测试锚定）。 */

export const THEMES: {id: string; label: string}[] = [
  {id: "", label: "默认"},
  {id: "academic", label: "学术"},
];

export function currentTheme(): string {
  return document.documentElement.getAttribute("data-theme")
    ?? localStorage.getItem("weft-theme") ?? "";
}

export function applyTheme(id: string): void {
  if (id) {
    document.documentElement.setAttribute("data-theme", id);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  try {
    localStorage.setItem("weft-theme", id);
  } catch {
    /* 静默降级（隐私模式等） */
  }
}

/** 循环切换到下一主题（Topbar 单按钮语义，与旧 webui.js 一致）。 */
export function cycleTheme(): void {
  const cur = currentTheme();
  const idx = THEMES.findIndex((t) => t.id === cur);
  applyTheme(THEMES[(idx + 1) % THEMES.length].id);
}
