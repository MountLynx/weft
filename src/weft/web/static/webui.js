// weft WebUI 交互：SSE 进度流（Task 11 消费）+ uses 行克隆（webui 设计 §5/§6）。
function addUseRow() {
  const rows = document.getElementById("use-rows");
  if (!rows) return;
  const tpl = rows.querySelector(".use-row");
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
      const ev = JSON.parse(m.data);
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
  });
}

document.addEventListener("DOMContentLoaded", function () { connectRunStream(document); });
document.addEventListener("htmx:afterSwap", function (evt) { connectRunStream(evt.target); });
