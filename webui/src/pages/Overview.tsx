/** 总览：统计卡 + bib 模式行 + 待审阅队列（dashboard payload 驱动）。 */
import {Link, useNavigate, useParams} from "react-router-dom";
import type {Dashboard} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {kindIcon} from "../components/kinds";
import {EmptyState} from "../components/EmptyState";

export function Overview() {
  const {pid = ""} = useParams();
  const navigate = useNavigate();
  const {data: dash} = useApi<Dashboard>(`/api/projects/${encodeURIComponent(pid)}`);

  if (!dash) return null;
  if (!dash.available && !dash.kind_counts) {
    // 加载级损坏：无项目对象可看（unavailable 语义）
    return (
      <main className="center">
        <div className="page-head"><h2>{pid}</h2></div>
        <div className="page-body">
          <div className="banner error">
            <div>无法加载项目（加载级损坏），先看诊断：</div>
            {(dash.diagnostics ?? []).map((d, i) => (
              <span key={i} className="field-error">
                {d.path} [{d.code}] {d.message}
              </span>
            ))}
          </div>
        </div>
      </main>
    );
  }

  const sc = dash.status_counts ?? {};
  const kc = dash.kind_counts ?? {};

  return (
    <main className="center">
      <div className="page-head">
        <h2>总览</h2>
        <span className="spacer" />
        {dash.available === false && <span className="badge danger">不可用</span>}
        <Link to={`/p/${encodeURIComponent(pid)}/diagnostics`} className="btn"
              style={{display: "inline-flex", alignItems: "center", gap: 6}}>
          <Icon name="pulse" size={14} />诊断
        </Link>
      </div>
      <div className="page-body">
        <div className="stats">
          <div className="stat-card">
            <span className="num">{dash.n_cards ?? 0}</span>
            <span className="label">卡片</span>
          </div>
          <div className="stat-card">
            <span className="num">{dash.n_parts ?? 0}</span>
            <span className="label">叙事 part</span>
          </div>
          <div className="stat-card">
            <span className="num">{sc.approved ?? 0}</span>
            <span className="label">approved</span>
          </div>
          <div className="stat-card">
            <span className="num">{sc.draft ?? 0}</span>
            <span className="label">draft</span>
          </div>
          <div className="stat-card">
            <span className="num" style={{color: (dash.n_errors ?? 0) > 0 ? "var(--danger)" : undefined}}>
              {dash.n_errors ?? 0}
            </span>
            <span className="label">错误</span>
          </div>
          <div className="stat-card">
            <span className="num">{dash.n_warnings ?? 0}</span>
            <span className="label">提醒</span>
          </div>
        </div>
        <div className="banner">
          <div>
            bib 模式：<span className="badge mono">{dash.bib_managed ? "managed" : "unmanaged"}</span>
            {"  "}
            <span className="text-xs text-muted">{(dash.bib_files ?? []).join("、")}</span>
          </div>
          <div>
            <Link to={`/p/${encodeURIComponent(pid)}/bib-switch?to=${dash.bib_managed ? "unmanaged" : "managed"}`}>
              切换为 {dash.bib_managed ? "unmanaged" : "managed"}
            </Link>
          </div>
        </div>
        <div>
          <h3 style={{margin: "6px 0", fontSize: "var(--fs-base)", color: "var(--text-heading)"}}>
            待审阅（{(dash.review_queue ?? []).length}）
          </h3>
          {(dash.review_queue ?? []).length === 0 ? (
            <EmptyState icon="check" hint="没有待审阅的卡片或节点" />
          ) : (
            <div className="row-list">
              {(dash.review_queue ?? []).map((q, i) => (
                <a key={i} className="row-item"
                   onClick={(e) => {
                     e.preventDefault();
                     if (q.type === "card") {
                       navigate(`/p/${encodeURIComponent(pid)}/cards/${q.card_kind}/${q.id}`);
                     } else {
                       navigate(`/p/${encodeURIComponent(pid)}/parts/${q.part_id}/nodes/${q.id}`);
                     }
                   }}>
                  <Icon name={q.type === "card" ? kindIcon(q.card_kind) : "layers"} size={15} />
                  <div className="main">
                    <span className="title">{q.id}</span>
                    <span className="meta text-muted">{q.label} · {q.rel}</span>
                  </div>
                  <span className="end badge accent">{q.label}</span>
                </a>
              ))}
            </div>
          )}
        </div>
        <div className="text-xs text-muted">
          卡片分布：{Object.entries(kc).map(([k, v]) => `${k} ${v}`).join(" · ")}
        </div>
      </div>
    </main>
  );
}
