// weft WebUI 交互：SSE 进度流（Task 11 消费）+ uses 行克隆（webui 设计 §5/§6）。
function addUseRow() {
  const rows = document.getElementById("use-rows");
  if (!rows) return;
  const tpl = rows.querySelector(".use-row");
  if (!tpl) return;                    // 全部行被移除后克隆源不存在：静默返回（刷新恢复）
  const clone = tpl.cloneNode(true);
  clone.querySelectorAll("input").forEach(function (el) { el.value = ""; });
  rows.appendChild(clone);
}

function connectRunStream(scope) {
  (scope || document).querySelectorAll("[data-run-id]").forEach(function (el) {
    if (el.dataset.streamBound) return;
    el.dataset.streamBound = "1";
    const src = new EventSource(el.dataset.eventsUrl);
    src.onmessage = function (m) {
      let ev;
      try { ev = JSON.parse(m.data); } catch (err) { return; }
      const line = document.createElement("div");
      line.className = "log-" + ev.kind;
      line.textContent = (ev.node_id ? ev.node_id + " · " : "") +
        ev.kind + (ev.message ? " — " + ev.message : "");
      el.appendChild(line);
      if (ev.kind === "run_finished" || ev.kind === "run_failed") {
        src.close();
        const panel = el.closest("[data-panel-url]");
        if (panel && window.htmx) {
          htmx.ajax("GET", panel.dataset.panelUrl, panel);   // 完成后刷新面板（草稿预览）
        }
      }
    };
    src.onerror = function () { src.close(); };
  });
}

document.addEventListener("DOMContentLoaded", function () { connectRunStream(document); });
document.addEventListener("htmx:afterSwap", function (evt) { connectRunStream(evt.target); });

// 主题切换（2026-09-09 样式设计 §6）：localStorage 持久化 + <html data-theme> 驱动令牌。
// 主题注册表：新增主题 = themes/<id>.css + base.html 的 <link> 与按钮 + 此处一项。
const THEMES = [
  { id: "", label: "☀ 默认" },
  { id: "academic", label: "📜 学术" },
];

function applyTheme(id) {
  if (!THEMES.some(function (t) { return t.id === id; })) id = "";
  if (id) document.documentElement.setAttribute("data-theme", id);
  else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("weft-theme", id); } catch (e) { /* 隐私模式静默 */ }
}

function initThemeToggle() {
  const box = document.getElementById("theme-toggle");
  if (!box) return;
  const current = document.documentElement.getAttribute("data-theme") || "";
  box.querySelectorAll("button[data-theme-id]").forEach(function (btn) {
    if ((btn.getAttribute("data-theme-id") || "") === current) btn.classList.add("active");
    btn.addEventListener("click", function () {
      applyTheme(btn.getAttribute("data-theme-id") || "");
      box.querySelectorAll("button").forEach(function (b) { b.classList.remove("active"); });
      btn.classList.add("active");
    });
  });
}

document.addEventListener("DOMContentLoaded", initThemeToggle);
