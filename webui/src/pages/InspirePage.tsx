/** 灵感页：文本段 → 灵感管线（SSE 控制台）+ 提案列表（对比/应用）。 */
import {useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {InspireList} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {RunConsole} from "../components/RunConsole";
import {toast} from "../state/toast";

export function InspirePage() {
  const {pid = ""} = useParams();
  const navigate = useNavigate();
  const {data, reload} = useApi<InspireList>(
    `/api/projects/${encodeURIComponent(pid)}/inspire`);
  const [text, setText] = useState("");
  const [mock, setMock] = useState(false);
  const [runId, setRunId] = useState("");
  const [error, setError] = useState("");
  const [applying, setApplying] = useState("");

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setRunId("");
    try {
      const resp = await api.post<{ok: boolean; run_id: string}>(
        `/api/projects/${encodeURIComponent(pid)}/inspire/run`,
        {text, mock});
      setRunId(resp.run_id);
      navigate(`/p/${encodeURIComponent(pid)}/runs/${resp.run_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function apply(cardId: string) {
    setApplying(cardId);
    try {
      const resp = await api.post<{ok: boolean}>(
        `/api/projects/${encodeURIComponent(pid)}/inspire/proposals/${encodeURIComponent(cardId)}/apply`);
      if (resp.ok) toast.success(`提案已应用：${cardId}`);
      else toast.info(`提案 ${cardId} 不可应用（已被拒绝或不存在）`);
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setApplying("");
    }
  }

  return (
    <main className="center">
      <div className="page-head"><h2>灵感</h2></div>
      <div className="page-body">
        <form className="form" onSubmit={run} style={{maxWidth: "none"}}>
          <div className="form-row">
            <label>灵感文本（想法、文献笔记、一段话——管线会拆解为卡片提案）</label>
            <textarea rows={5} value={text} placeholder="粘贴一段灵感…"
                      onChange={(e) => setText(e.target.value)} />
          </div>
          <div className="form-row">
            <div className="row-inline">
              <label className="text-xs text-muted" style={{display: "flex", alignItems: "center", gap: 4}}>
                <input type="checkbox" checked={mock} style={{width: 14, height: 14}}
                       onChange={(e) => setMock(e.target.checked)} />
                mock（不发真实 LLM）
              </label>
              <span className="spacer" style={{flex: 1}} />
              <button type="submit" className="primary">
                <Icon name="play" size={14} />运行灵感管线
              </button>
            </div>
          </div>
          {error && <div className="banner error">{error}</div>}
        </form>
        {runId && <RunConsole pid={pid} runId={runId} onFinished={reload} />}
        <div>
          <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--text-heading)"}}>
            替换提案（{(data?.proposals ?? []).length}）
          </h3>
          {(data?.proposals ?? []).length === 0 ? (
            <div className="text-muted text-sm" style={{padding: "12px 0"}}>
              暂无提案——灵感管线产出的卡片替换提案会出现在这里。
            </div>
          ) : (
            <div className="row-list">
              {(data?.proposals ?? []).map((p) => (
                <div key={p.id} className="row-item" style={{cursor: "default"}}>
                  <Icon name="inbox" size={15} />
                  <div className="main">
                    <span className="title">{p.id}</span>
                    <span className="meta text-muted">inspirations/proposals/{p.id}.md</span>
                  </div>
                  <span className="end">
                    <Link className="btn"
                          to={`/p/${encodeURIComponent(pid)}/inspire/proposals/${encodeURIComponent(p.id)}`}>
                      对比
                    </Link>
                    <button className="primary" disabled={applying === p.id}
                            onClick={() => apply(p.id)}>
                      <Icon name="check" size={14} />应用
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
