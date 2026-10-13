/** Sidebar：section 导航 + 卡片 kind 分组（dashboard payload 驱动显示/收缩）。 */
import {NavLink, useParams} from "react-router-dom";
import type {Dashboard} from "../api/types";
import {Icon} from "./Icon";

const KIND_ORDER = ["data", "fact", "claim", "note", "method", "param"] as const;

export function Sidebar({dash}: {dash: Dashboard | null}) {
  const {pid = ""} = useParams();
  const base = `/p/${encodeURIComponent(pid)}`;
  const counts = dash?.kind_counts ?? {};
  const kindLabels: Record<string, string> = {
    data: "data", fact: "fact", claim: "claim",
    note: "note", method: "method", param: "param",
  };

  return (
    <nav className="sidebar">
      <div className="section-label">导航</div>
      <NavLink to={base} end className="nav-item">
        <Icon name="home" size={14} />总览
      </NavLink>
      {(dash?.n_parts ?? 0) > 0 && (
        <NavLink to={`${base}/parts`} className="nav-item">
          <Icon name="layers" size={14} />叙事
          <span className="count">{dash?.n_parts}</span>
        </NavLink>
      )}
      <NavLink to={`${base}/cards`} className="nav-item">
        <Icon name="file-text" size={14} />卡片
        <span className="count">{dash?.n_cards ?? ""}</span>
      </NavLink>
      <NavLink to={`${base}/figures`} className="nav-item">
        <Icon name="image" size={14} />图表
      </NavLink>
      <NavLink to={`${base}/graph`} className="nav-item">
        <Icon name="network" size={14} />图谱
      </NavLink>
      <NavLink to={`${base}/inspire`} className="nav-item">
        <Icon name="bulb" size={14} />灵感
      </NavLink>
      <NavLink to={`${base}/diagnostics`} className="nav-item">
        <Icon name="pulse" size={14} />诊断
        {(dash?.n_errors ?? 0) > 0 && <span className="count">{dash?.n_errors}</span>}
      </NavLink>
      <div className="section-label">卡片</div>
      {KIND_ORDER.map((kind) => (
        <NavLink key={kind} to={`${base}/cards/${kind}`} className="nav-item sub">
          {kindLabels[kind]}
          <span className="count">{counts[kind] ?? 0}</span>
        </NavLink>
      ))}
    </nav>
  );
}
