/** 替换提案对比：字段对照（changed 高亮）+ 逐行统一 diff；fail-closed 隐藏应用。 */
import {useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {ComparePayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {toast} from "../state/toast";

export function ProposalComparePage() {
  const {pid = "", cardId = ""} = useParams();
  const navigate = useNavigate();
  const {data, reload} = useApi<ComparePayload>(
    `/api/projects/${encodeURIComponent(pid)}/inspire/proposals/${encodeURIComponent(cardId)}`);
  const [applying, setApplying] = useState(false);

  async function apply() {
    setApplying(true);
    try {
      const resp = await api.post<{ok: boolean}>(
        `/api/projects/${encodeURIComponent(pid)}/inspire/proposals/${encodeURIComponent(cardId)}/apply`);
      if (resp.ok) {
        toast.success(`提案已应用：${cardId}`);
        navigate(`/p/${encodeURIComponent(pid)}/inspire`);
      } else {
        toast.info(`提案 ${cardId} 不可应用`);
        reload();
      }
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setApplying(false);
    }
  }

  return (
    <main className="center">
      <div className="page-head">
        <h2>提案对比 · {cardId}</h2>
        <span className="spacer" />
        <Link className="btn" to={`/p/${encodeURIComponent(pid)}/inspire`}>
          <Icon name="arrow-left" size={14} />返回灵感
        </Link>
        {data?.applicable && (
          <button className="primary" onClick={apply} disabled={applying}>
            <Icon name="check" size={14} />应用提案
          </button>
        )}
      </div>
      <div className="page-body">
        {data?.warn && <div className="banner error">{data.warn}</div>}
        {data?.rows && (
          <div className="compare-table">
            {(data.rows ?? []).map((r) => (
              <div key={r.key} className={`compare-row${r.changed ? " changed" : ""}`}>
                <span className="k">{r.key}</span>
                <span className="v">
                  {r.changed
                    ? <div>
                        <div className="text-xs text-muted">当前 → 提案</div>
                        <pre style={{color: "var(--danger)"}}>- {r.old || "（空）"}</pre>
                        <pre style={{color: "var(--success)"}}>+ {r.new || "（空）"}</pre>
                      </div>
                    : <pre>{r.new || "（空）"}</pre>}
                </span>
              </div>
            ))}
          </div>
        )}
        {data?.diff_rows && (
          <div>
            <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--text-heading)"}}>
              逐行 diff
            </h3>
            <div className="diff-table">
              {(data.diff_rows ?? []).map((l, i) => (
                <div key={i} className={`diff-line ${l.cls}`}>
                  <span className="no">{i + 1}</span>
                  <span className="code">{l.text}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {data?.raw_new && (
          <div>
            <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--text-heading)"}}>
              提案原文
            </h3>
            <div className="file-preview">{data.raw_new}</div>
          </div>
        )}
      </div>
    </main>
  );
}
