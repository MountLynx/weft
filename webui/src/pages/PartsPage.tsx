/** 叙事工作台：part 页签 + 面板（工作流覆盖 / 节点快捷审阅 / 生成 / 草稿预览）。 */
import {useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {PartsList, PanelPayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {RunConsole} from "../components/RunConsole";
import {StatusBadge} from "../components/StatusBadge";
import {toast} from "../state/toast";

export function PartsPage() {
  const {pid = "", partId} = useParams();
  const navigate = useNavigate();
  const {data: list, error: listError} = useApi<PartsList>(
    `/api/projects/${encodeURIComponent(pid)}/parts`);
  const current = partId ?? list?.first;
  const {data: panel, reload} = useApi<PanelPayload>(
    current
      ? `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(current)}`
      : null);
  const [mock, setMock] = useState(false);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");

  if (listError) {
    // 404 = 项目没有叙事 part（前端据此出空态，语义同旧 subnav 隐藏"叙事"入口）
    return (
      <main className="center">
        <div className="page-head"><h2>叙事</h2></div>
        <div className="page-body">
          <div className="empty-state">
            <span className="big-icon"><Icon name="layers" size={56} /></span>
            <div className="hint">项目没有叙事 part</div>
          </div>
        </div>
      </main>
    );
  }
  if (!list || !current) return <main className="center" />;

  async function reviewNode(nodeId: string, status: string) {
    if (!current) return;
    try {
      await api.post(
        `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(current)}/nodes/${encodeURIComponent(nodeId)}/status`,
        {status});
      toast.success(`${nodeId} → ${status}`);
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function saveWorkflow(workflow: string) {
    if (!current) return;
    try {
      await api.post(
        `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(current)}/workflow`,
        {workflow});
      toast.success(workflow ? `workflow 覆盖：${workflow}` : "已恢复自动路由");
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function generate() {
    if (!current) return;
    setError("");
    setRunId("");
    try {
      const resp = await api.post<{ok: boolean; run_id: string}>(
        `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(current)}/generate`,
        {mock});
      setRunId(resp.run_id);
      navigate(`/p/${encodeURIComponent(pid)}/runs/${resp.run_id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.diagnostics
          ? `${err.detail}\n` + err.diagnostics
            .filter((d) => d.is_error)
            .map((d) => `${d.path} [${d.code}] ${d.message}`).join("\n")
          : err.detail);
      } else {
        setError(String(err));
      }
    }
  }

  return (
    <main className="center">
      <div className="tabs">
        {(list?.parts ?? []).map((p) => (
          <Link key={p.id}
                to={`/p/${encodeURIComponent(pid)}/parts/${p.id}`}
                className={`tab${p.id === current ? " active" : ""}`}>
            {p.id}（{p.n_nodes} 节点）
          </Link>
        ))}
      </div>
      <div className="page-head">
        <h2>{current}</h2>
        <span className="spacer" />
        <label className="text-xs text-muted" style={{display: "flex", alignItems: "center", gap: 4}}>
          <input type="checkbox" checked={mock} style={{width: 14, height: 14}}
                 onChange={(e) => setMock(e.target.checked)} />
          mock（不发真实 LLM）
        </label>
        <button className="primary" onClick={generate}>
          <Icon name="play" size={14} />生成草稿
        </button>
      </div>
      <div className="page-body">
        {error && <div className="banner error" style={{whiteSpace: "pre-wrap"}}>{error}</div>}
        <div className="form-row">
          <label>workflow 覆盖（空 = 走 chapter 自动路由）</label>
          <div className="row-inline">
            <select defaultValue={panel?.part.workflow ?? ""}
                    onChange={(e) => saveWorkflow(e.target.value)}>
              <option value="">（自动路由）</option>
              {(panel?.workflow_vocab ?? []).map((w) => (
                <option key={w} value={w}>{w}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="row-list">
          {(panel?.nodes ?? []).map((n) => (
            <div key={n.id} className="row-item" style={{cursor: "default"}}>
              <Icon name="layers" size={15} />
              <div className="main">
                <span className="title">{n.id}</span>
                <span className="meta text-muted truncate">
                  {n.purpose}
                  {n.uses.length > 0 && ` · 使用 ${n.uses.map((u) => {
                    const label = panel?.use_labels[u.id];
                    return label ? `${u.id}(${u.role}) · ${label}` : `${u.id}(${u.role})`;
                  }).join("；")}`}
                </span>
              </div>
              <span className="end">
                <StatusBadge status={n.status} />
                <Link className="icon-btn" title="编辑"
                      to={`/p/${encodeURIComponent(pid)}/parts/${encodeURIComponent(current)}/nodes/${encodeURIComponent(n.id)}`}>
                  <Icon name="pencil" size={14} />
                </Link>
                <button className="icon-btn" title="批准"
                        onClick={() => reviewNode(n.id, "approved")}>
                  <Icon name="check" size={14} />
                </button>
                <button className="icon-btn danger" title="否决"
                        onClick={() => reviewNode(n.id, "rejected")}>
                  <Icon name="x" size={14} />
                </button>
              </span>
            </div>
          ))}
        </div>
        {runId && <RunConsole pid={pid} runId={runId} onFinished={reload} />}
        {panel?.draft_text && (
          <div>
            <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--text-heading)"}}>
              草稿预览
            </h3>
            <div className="draft-preview">{panel.draft_text}</div>
          </div>
        )}
      </div>
    </main>
  );
}
