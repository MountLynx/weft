/** Topbar：brand + 项目切换下拉 + 主题循环切换（itemmanage Titlebar 范式的浏览器版）。 */
import {useEffect, useRef, useState} from "react";
import {Link, useNavigate, useParams} from "react-router-dom";
import type {ProjectsIndex} from "../api/types";
import {useApi} from "../hooks/useApi";
import {cycleTheme} from "../state/theme";
import {Icon} from "./Icon";

export function Topbar() {
  const {pid = ""} = useParams();
  const navigate = useNavigate();
  const {data} = useApi<ProjectsIndex>("/api/projects");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const fn = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", fn);
    return () => document.removeEventListener("mousedown", fn);
  }, []);

  const entries = data?.entries ?? [];
  const current = entries.find((e) => e.pid === pid);
  const available = entries.filter((e) => !e.missing);

  return (
    <header className="topbar">
      <Link to="/" className="brand"><Icon name="database" size={17} />weft</Link>
      {pid && (
        <>
          <div className="project-switcher" ref={ref}>
            <button onClick={() => setOpen(!open)}>
              <Icon name="layers" size={14} />
              {current?.pid ?? pid}
              <Icon name="chevron-down" size={13} />
            </button>
            {open && (
              <div className="menu">
                {available.map((e) => (
                  <Link key={e.pid} className={e.pid === pid ? "current" : ""}
                        to={`/p/${encodeURIComponent(e.pid)}`}
                        onClick={() => setOpen(false)}>
                    <Icon name="file-text" size={13} />
                    {e.pid}
                    <span className="end text-xs text-muted">
                      {e.available ? `${e.n_cards} 卡` : "不可用"}
                    </span>
                  </Link>
                ))}
                {entries.filter((e) => e.missing).map((e) => (
                  <span key={e.pid} className="menu-note text-xs text-muted"
                        style={{display: "block", padding: "4px 10px"}}>
                    {e.pid}（位置失联）
                  </span>
                ))}
                <Link to="/" onClick={() => setOpen(false)}>
                  <Icon name="home" size={13} />全部项目…
                </Link>
              </div>
            )}
          </div>
          {current && !current.available && (
            <span className="badge danger">不可用</span>
          )}
        </>
      )}
      <span className="spacer" />
      <button className="icon-btn" title="切换主题"
              onClick={() => cycleTheme()}>
        <Icon name="sun" size={16} />
      </button>
      <span className="divider" />
      <button className="ghost" onClick={() => navigate("/")}>
        <Icon name="home" size={14} />项目列表
      </button>
    </header>
  );
}
