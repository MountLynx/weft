/** 项目网格（首态）：卡片网格 + 新建项目模态（itemmanage RepoDashboard 范式）。 */
import {useState} from "react";
import {Link, useNavigate} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {ProjectsIndex} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {Modal} from "../components/Modal";
import {toast} from "../state/toast";

export function ProjectsGrid() {
  const navigate = useNavigate();
  const {data, error} = useApi<ProjectsIndex>("/api/projects");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [formError, setFormError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    try {
      const body = location.trim()
        ? {name, location: location.trim()}
        : {name};
      const resp = await api.post<{ok: boolean; pid: string}>("/api/projects", body);
      toast.success(`项目 ${resp.pid} 已创建`);
      setCreating(false);
      navigate(`/p/${encodeURIComponent(resp.pid)}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <div className="grid-page">
      <div className="grid-head">
        <div className="logo"><Icon name="database" size={22} /></div>
        <h1>weft</h1>
        <div className="tagline">AI 学术写作引擎 —— 卡片为经，叙事为纬</div>
        {error && <div className="reg-error">{error.detail}</div>}
        {!error && data?.reg_error && <div className="reg-error">{data.reg_error}</div>}
      </div>
      <div className="card-grid">
        {(data?.entries ?? []).map((e) => (
          <Link key={e.pid}
                to={e.missing ? "#" : `/p/${encodeURIComponent(e.pid)}`}
                className={`project-card${e.available ? "" : " unavailable"}`}
                style={e.missing ? {opacity: 0.55, pointerEvents: "none"} : undefined}>
            <div className="name truncate">{e.pid}</div>
            <div className="meta truncate">{e.n_cards} 张卡 · {e.path}</div>
            <div className="badges">
              {e.missing && <span className="badge danger">位置失联</span>}
              {!e.missing && e.available && <span className="badge success">可用</span>}
              {!e.missing && !e.available && <span className="badge danger">不可用</span>}
              {e.n_errors > 0 && <span className="badge danger">E: {e.n_errors}</span>}
              {e.n_warnings > 0 && <span className="badge warning">W: {e.n_warnings}</span>}
            </div>
          </Link>
        ))}
        <button className="create-tile" onClick={() => setCreating(true)}>
          <Icon name="plus" size={20} />
          新建项目
        </button>
      </div>
      {creating && (
        <Modal title="新建项目" onClose={() => setCreating(false)}>
          <form className="form" onSubmit={submit}>
            <div className="form-row">
              <label>项目名</label>
              <input autoFocus value={name} placeholder="如 paper-2026"
                     onChange={(e) => setName(e.target.value)} />
            </div>
            {data?.registry_mode && (
              <div className="form-row">
                <label>位置（留空用默认根：{data.registry_path}）</label>
                <input value={location} placeholder="项目父目录"
                       onChange={(e) => setLocation(e.target.value)} />
              </div>
            )}
            {formError && <div className="form-error">{formError}</div>}
            <div className="form-actions">
              <button type="button" className="ghost" onClick={() => setCreating(false)}>
                取消
              </button>
              <button type="submit" className="primary">创建</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
