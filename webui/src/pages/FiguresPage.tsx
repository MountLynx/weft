/** 图表注册表：行列表 + 新增/编辑（错误带 values 回显保真）。 */
import {useState} from "react";
import {useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {FiguresPayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {Modal} from "../components/Modal";
import {toast} from "../state/toast";

interface FormState {
  key: string | null;           // null = 新增
  caption: string;
  subfigs: string;
  prefix: string;
}

export function FiguresPage() {
  const {pid = ""} = useParams();
  const {data, reload} = useApi<FiguresPayload>(
    `/api/projects/${encodeURIComponent(pid)}/figures`);
  const [form, setForm] = useState<FormState | null>(null);

  const readonly = data?.load_error !== null && data?.load_error !== undefined;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    try {
      if (form.key === null) {
        await api.post(`/api/projects/${encodeURIComponent(pid)}/figures`,
                       {key: "", caption: form.caption, subfigs: form.subfigs,
                        prefix: form.prefix});
      } else {
        await api.patch(`/api/projects/${encodeURIComponent(pid)}/figures/${encodeURIComponent(form.key)}`,
                        {caption: form.caption, subfigs: form.subfigs});
      }
      toast.success("figures.yaml 已保存");
      setForm(null);
      reload();
    } catch (err) {
      if (err instanceof ApiError) {
        toast.error(err.detail);
        if (err.values) {
          setForm((f) => f && ({
            ...f,
            key: String(err.values?.key ?? f.key),
            caption: String(err.values?.caption ?? f.caption),
            subfigs: String(err.values?.subfigs ?? f.subfigs),
            prefix: String(err.values?.prefix ?? f.prefix),
          }));
        }
      } else {
        toast.error(String(err));
      }
    }
  }

  async function remove(key: string) {
    try {
      await api.post(`/api/projects/${encodeURIComponent(pid)}/figures/${encodeURIComponent(key)}/delete`);
      toast.success(`已删除 ${key}`);
      reload();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    }
  }

  return (
    <main className="center">
      <div className="page-head">
        <h2>图表</h2>
        <span className="spacer" />
        <button className="primary" disabled={readonly}
                onClick={() => setForm({key: null, caption: "", subfigs: "", prefix: "fig"})}>
          <Icon name="plus" size={14} />新增图注条目
        </button>
      </div>
      <div className="page-body">
        {data?.load_error && <div className="banner error">
          {data.load_error}（页面只读）
        </div>}
        {(data?.rows ?? []).length === 0 && !data?.load_error ? (
          <div className="empty-state">
            <span className="big-icon"><Icon name="image" size={56} /></span>
            <div className="hint">figures.yaml 还没有条目</div>
          </div>
        ) : (
          <div className="row-list">
            {(data?.rows ?? []).map((r) => (
              <div key={r.key} className="row-item" style={{cursor: "default"}}>
                <Icon name={r.kind === "table" ? "file-text" : "image"} size={15} />
                <div className="main">
                  <span className="title">{r.key}</span>
                  <span className="meta text-muted truncate">
                    {r.caption}
                    {Object.keys(r.subfigs).length > 0
                      && ` · 子图 ${Object.keys(r.subfigs).join("/")}`}
                  </span>
                </div>
                <span className="end">
                  {r.file_missing && <span className="badge warning">文件缺失</span>}
                  {r.unused && <span className="badge warning">未被引用</span>}
                  {r.used_by.length > 0 && (
                    <span className="badge mono" title={r.used_by.join("、")}>
                      {r.used_by.length} 卡引用
                    </span>
                  )}
                  <button className="icon-btn" title="编辑" disabled={readonly}
                          onClick={() => {
                            setForm({
                              key: r.key, caption: r.caption,
                              subfigs: Object.entries(r.subfigs)
                                .map(([s, c]) => `${s}: ${c}`).join("\n"),
                              prefix: "fig",
                            });
                          }}>
                    <Icon name="pencil" size={14} />
                  </button>
                  <button className="icon-btn danger" title="删除" disabled={readonly}
                          onClick={() => remove(r.key)}>
                    <Icon name="x" size={14} />
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
      {form && (
        <Modal title={form.key === null ? "新增图注条目" : `编辑 ${form.key}`}
               onClose={() => setForm(null)}>
          <form className="form" onSubmit={submit}>
            {form.key === null && (
              <div className="form-row">
                <label>类型前缀</label>
                <div className="row-inline">
                  <label className="badge" style={{cursor: "pointer"}}>
                    <input type="radio" name="prefix" checked={form.prefix === "fig"}
                           onChange={() => setForm({...form, prefix: "fig"})} />fig- 图
                  </label>
                  <label className="badge" style={{cursor: "pointer"}}>
                    <input type="radio" name="prefix" checked={form.prefix === "tbl"}
                           onChange={() => setForm({...form, prefix: "tbl"})} />tbl- 表
                  </label>
                  <input placeholder="留空自动编号（可自定义键名）" style={{flex: 1}}
                         value={form.key ?? ""} onChange={(e) => setForm({...form, key: e.target.value})} />
                </div>
              </div>
            )}
            <div className="form-row">
              <label>caption（题注）</label>
              <input autoFocus value={form.caption}
                     onChange={(e) => setForm({...form, caption: e.target.value})} />
            </div>
            <div className="form-row">
              <label>subfigs（每行一个：子图号: 说明）</label>
              <textarea rows={4} spellCheck={false} value={form.subfigs}
                        placeholder={"a: 60°C\nb: 80°C"}
                        onChange={(e) => setForm({...form, subfigs: e.target.value})} />
            </div>
            <div className="form-actions">
              <button type="button" className="ghost" onClick={() => setForm(null)}>取消</button>
              <button type="submit" className="primary">保存</button>
            </div>
          </form>
        </Modal>
      )}
    </main>
  );
}
