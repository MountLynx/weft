/** Sidebar：section 导航 + 卡片 kind 折叠组（挂在「卡片」项下，默认收缩、点击开合）。 */
import {useRef, useState} from "react";
import {NavLink, useLocation, useParams} from "react-router-dom";
import type {Dashboard} from "../api/types";
import {Icon} from "./Icon";
import {KINDS, KIND_ICONS} from "./kinds";
import {CardFilterPanel} from "./CardFilterPanel";

export function Sidebar({dash}: {dash: Dashboard | null}) {
  const {pid = ""} = useParams();
  const {pathname} = useLocation();
  const base = `/p/${encodeURIComponent(pid)}`;
  const counts = dash?.kind_counts ?? {};

  // 卡片组展开态：路由默认值（/cards/* 下展开，其他页收缩），点「卡片」手动开合；
  // 路由进出卡片区的那一帧重置回路由默认（渲染期同步范式，与 useApi 一致）。
  const onCards = pathname.startsWith(`${base}/cards`);
  const [manual, setManual] = useState<boolean | null>(null);
  const prevOnCards = useRef(onCards);
  if (prevOnCards.current !== onCards) {
    prevOnCards.current = onCards;
    if (manual !== null) setManual(null);
  }
  const open = manual ?? onCards;

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
      <NavLink to={`${base}/cards`} className="nav-item"
               onClick={(e) => {
                 if (open) {
                   e.preventDefault();      // 收起 = 纯 UI 开合，不换页
                   setManual(false);
                 } else {
                   setManual(true);         // 展开，NavLink 照常跳卡片页
                 }
               }}>
        <Icon name="file-text" size={14} />卡片
        <span className="count">{dash?.n_cards ?? ""}</span>
        <Icon name="chevron-down" size={13} className={`chev${open ? "" : " closed"}`} />
      </NavLink>
      {open && KINDS.map((kind) => (
        <NavLink key={kind} to={`${base}/cards/${kind}`} className="nav-item sub">
          <Icon name={KIND_ICONS[kind]} size={14} />
          {kind}
          <span className="count">{counts[kind] ?? 0}</span>
        </NavLink>
      ))}
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
      <CardFilterPanel />
    </nav>
  );
}
