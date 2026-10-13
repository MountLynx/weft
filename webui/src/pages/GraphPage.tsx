/** 图谱：cytoscape 运行时注入渲染（vendored 脚本，不进 bundle，设计 D6）。 */
import {useEffect, useRef, useState} from "react";
import {useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {GraphPayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {toast} from "../state/toast";

interface EntEntry {
  kind: string;
  referenced_by?: Record<string, string[]>;
}

const KIND_COLORS: Record<string, string> = {
  data: "#8250df", fact: "#0969da", claim: "#1a7f37",
  note: "#bf8700", method: "#cf222e", param: "#57606a",
};

declare global {
  interface Window {
    cytoscape?: ((opts: Record<string, unknown>) => unknown) & {known?: boolean};
  }
}

function loadCytoscape(): Promise<void> {
  if (window.cytoscape) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "/static/cytoscape.min.js";
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("cytoscape 加载失败"));
    document.head.appendChild(s);
  });
}

/** graph.json（entities 字典）→ cytoscape elements（语义同旧 graph.html 内联脚本）。 */
function buildElements(graph: Record<string, unknown>): unknown[] {
  const ents = ((graph.entities ?? graph) ?? {}) as Record<string, EntEntry>;
  const els: unknown[] = [];
  const seen = new Set<string>();
  for (const [id, e] of Object.entries(ents)) {
    seen.add(id);
    els.push({data: {id, label: id, kind: e.kind,
                     color: KIND_COLORS[e.kind] ?? "#57606a"}});
  }
  for (const [id, e] of Object.entries(ents)) {
    for (const ids of Object.values(e.referenced_by ?? {})) {
      for (const src of ids) {
        if (!seen.has(src)) {
          // 叙事节点 id 只出现在 referenced_by.nodes（非实体卡）
          seen.add(src);
          els.push({data: {id: src, label: src, kind: "node", color: "#8a8f98"}});
        }
        els.push({data: {id: `${src}->${id}`, source: src, target: id}});
      }
    }
  }
  return els;
}

export function GraphPage() {
  const {pid = ""} = useParams();
  const {data, reload} = useApi<GraphPayload>(
    `/api/projects/${encodeURIComponent(pid)}/graph`);
  const boxRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);

  const graph = data?.graph ?? null;

  useEffect(() => {
    if (!graph || !boxRef.current) return;
    let alive = true;
    loadCytoscape().then(() => {
      if (!alive || !window.cytoscape || !boxRef.current) return;
      window.cytoscape({
        container: boxRef.current,
        elements: buildElements(graph),
        style: [
          {selector: "node",
           style: {
             "background-color": "data(color)",
             label: "data(label)",
             color: "#555555",
             "font-size": 10,
             width: 24,
             height: 24,
           }},
          {selector: "edge",
           style: {
             width: 1,
             "line-color": "#DDDDDD",
             "target-arrow-color": "#DDDDDD",
             "target-arrow-shape": "triangle",
             "curve-style": "bezier",
           }},
        ],
        layout: {name: "cose", animate: false},
      });
    }).catch((err) => toast.error(String(err)));
    return () => {
      alive = false;
    };
  }, [graph]);

  async function regenerate() {
    setLoading(true);
    try {
      await api.post(`/api/projects/${encodeURIComponent(pid)}/graph/regenerate`);
      toast.success("图谱已生成");
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="center">
      <div className="page-head">
        <h2>图谱</h2>
        <span className="spacer" />
        <button className="primary" onClick={regenerate} disabled={loading}>
          <Icon name="refresh" size={14} />{loading ? "生成中…" : "生成图谱"}
        </button>
      </div>
      <div className="page-body full" style={{display: "flex", flex: 1}}>
        {graph ? (
          <div className="graph-wrap" ref={boxRef} />
        ) : (
          <div className="empty-state" style={{margin: "auto"}}>
            <span className="big-icon"><Icon name="network" size={56} /></span>
            <div className="hint">还没有图谱（generated/graph.json）——点右上「生成图谱」</div>
          </div>
        )}
      </div>
    </main>
  );
}
