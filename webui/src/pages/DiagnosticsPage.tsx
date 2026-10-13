/** 诊断页：诊断列表（E/W 分组）+ E-NOTE-NOT-IN-BIB 行内一键修复。 */
import {useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {DiagnosticsPayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {toast} from "../state/toast";

export function DiagnosticsPage() {
  const {pid = ""} = useParams();
  const navigate = useNavigate();
  const {data, reload} = useApi<DiagnosticsPayload>(
    `/api/projects/${encodeURIComponent(pid)}/diagnostics`);
  const [fixing, setFixing] = useState("");
  const [lastFix, setLastFix] = useState("");

  async function fix(key: string) {
    setFixing(key);
    try {
      const resp = await api.post<{ok: boolean; result: string}>(
        `/api/projects/${encodeURIComponent(pid)}/bib/fix/${encodeURIComponent(key)}`);
      setLastFix(resp.result);
      if (resp.result === "added") toast.success(`已把 ${key} 追加进 bib`);
      else if (resp.result === "present") toast.info(`bib 中已有 ${key}`);
      else toast.error("修复失败（bib 不可写或形状非法）");
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setFixing("");
    }
  }

  const errs = (data?.diagnostics ?? []).filter((d) => d.is_error);
  const warns = (data?.diagnostics ?? []).filter((d) => !d.is_error);

  const row = (d: (typeof errs)[number], i: number) => {
    const fixKey = data?.fixable[d.path] ?? (d.code === "E-NOTE-NOT-IN-BIB"
      ? d.message.split("：").pop()?.match(/[\w:-]+$/)?.[0] : undefined);
    return (
      <div key={i} className="row-item" style={{cursor: "default", alignItems: "flex-start"}}>
        <span className={`badge ${d.is_error ? "danger" : "warning"}`}>{d.code}</span>
        <div className="main">
          <span className="title text-xs font-mono">{d.path}{d.field ? ` · ${d.field}` : ""}</span>
          <span className="meta">{d.message}</span>
        </div>
        {d.code === "E-NOTE-NOT-IN-BIB" && fixKey && (
          <button disabled={fixing === fixKey} onClick={() => fix(fixKey)}>
            <Icon name="wrench" size={13} />一键修复
          </button>
        )}
      </div>
    );
  };

  return (
    <main className="center">
      <div className="page-head">
        <h2>诊断</h2>
        <span className="spacer" />
        <span className="badge danger">E: {errs.length}</span>
        <span className="badge warning">W: {warns.length}</span>
      </div>
      <div className="page-body">
        {lastFix && <div className="banner">
          最近修复结果：<span className="badge mono">{lastFix}</span>
        </div>}
        {errs.length === 0 && warns.length === 0 ? (
          <div className="empty-state">
            <span className="big-icon"><Icon name="check" size={56} /></span>
            <div className="hint">0 错误 0 提醒，项目健康</div>
          </div>
        ) : (
          <>
            {errs.length > 0 && (
              <>
                <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--danger)"}}>
                  错误（阻断）
                </h3>
                <div className="row-list">{errs.map(row)}</div>
              </>
            )}
            {warns.length > 0 && (
              <>
                <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--warning)"}}>
                  提醒（不阻断）
                </h3>
                <div className="row-list">{warns.map(row)}</div>
              </>
            )}
          </>
        )}
        <div className="text-xs text-muted">
          诊断码是稳定标识（E-*/W-*），总表见计划文档。
          <Link to={`/p/${encodeURIComponent(pid)}/cards`}
                onClick={(e) => { e.preventDefault(); navigate(`/p/${encodeURIComponent(pid)}/cards`); }}>
            → 去审卡
          </Link>
        </div>
      </div>
    </main>
  );
}
