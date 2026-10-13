/** 节点编辑：purpose/logic/uses 成对行（datalist + 实体速查）。 */
import {useState} from "react";
import {useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {NodeFormData} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {toast} from "../state/toast";

interface UseRow {
  id: string;
  role: string;
}

export function NodeFormPage() {
  const {pid = "", partId = "", nodeId = ""} = useParams();
  const navigate = useNavigate();
  const {data: form} = useApi<NodeFormData>(
    `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(partId)}/nodes/${encodeURIComponent(nodeId)}`);
  const [values, setValues] = useState<Record<string, unknown> | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  if (!form) return <main className="center" />;
  const v = values ?? form.values;
  const uses: UseRow[] = Array.isArray(v.use_id)
    ? (v.use_id as string[]).map((id, i) => ({
        id,
        role: ((v.use_role as string[]) ?? [])[i] ?? "",
      }))
    : [];

  function set(name: string, value: unknown) {
    setValues({...v, [name]: value});
  }

  function setUse(i: number, patch: Partial<UseRow>) {
    const next = uses.map((u, j) => (j === i ? {...u, ...patch} : u));
    set("use_id", next.map((u) => u.id));
    set("use_role", next.map((u) => u.role));
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErrors({});
    try {
      await api.patch(
        `/api/projects/${encodeURIComponent(pid)}/parts/${encodeURIComponent(partId)}/nodes/${encodeURIComponent(nodeId)}`,
        {purpose: v.purpose ?? "", logic: v.logic ?? "",
         status: v.status ?? "draft", comment: v.comment ?? "", uses});
      toast.success(`已保存 ${nodeId}`);
      navigate(`/p/${encodeURIComponent(pid)}/parts/${encodeURIComponent(partId)}`);
    } catch (err) {
      if (err instanceof ApiError && err.errors) {
        setErrors(err.errors);
        toast.error(err.detail);
      } else {
        toast.error(err instanceof ApiError ? err.detail : String(err));
      }
    }
  }

  return (
    <main className="center">
      <div className="page-head">
        <h2>编辑节点 {nodeId}</h2>
      </div>
      <div className="page-body">
        <form className="form" onSubmit={submit}>
          <div className="form-row">
            <label>purpose（叙述目的）</label>
            <input list="purpose-vocab" value={String(v.purpose ?? "")}
                   onChange={(e) => set("purpose", e.target.value)} />
            <datalist id="purpose-vocab">
              {form.purpose_vocab.map((p) => <option key={p} value={p} />)}
            </datalist>
            {errors.purpose && <span className="form-error">{errors.purpose}</span>}
          </div>
          <div className="form-row">
            <label>logic（叙事逻辑）</label>
            <textarea rows={3} value={String(v.logic ?? "")}
                      onChange={(e) => set("logic", e.target.value)} />
            {errors.logic && <span className="form-error">{errors.logic}</span>}
          </div>
          <div className="form-row">
            <label>uses（使用的实体 + 角色）</label>
            {uses.map((u, i) => (
              <div className="use-row" key={i}>
                <input list="entity-vocab" placeholder="实体 id"
                       value={u.id} onChange={(e) => setUse(i, {id: e.target.value})} />
                <input list="role-vocab" placeholder="角色"
                       value={u.role} onChange={(e) => setUse(i, {role: e.target.value})} />
                <button type="button" className="icon-btn danger" title="删除行"
                        onClick={() => {
                          const next = uses.filter((_, j) => j !== i);
                          set("use_id", next.map((x) => x.id));
                          set("use_role", next.map((x) => x.role));
                        }}>
                  <Icon name="x" size={14} />
                </button>
              </div>
            ))}
            <div>
              <button type="button"
                      onClick={() => {
                        set("use_id", [...uses.map((u) => u.id), ""]);
                        set("use_role", [...uses.map((u) => u.role), ""]);
                      }}>
                <Icon name="plus" size={13} />添加 use
              </button>
            </div>
            <datalist id="entity-vocab">
              {form.entity_ids.map((id) => (
                <option key={id} value={id}>
                  {form.entity_labels[id] ? `${id} · ${form.entity_labels[id]}` : id}
                </option>
              ))}
            </datalist>
            <datalist id="role-vocab">
              {form.role_vocab.map((r) => <option key={r} value={r} />)}
            </datalist>
            {errors.uses && <span className="form-error">{errors.uses}</span>}
          </div>
          <div className="form-row">
            <label>状态</label>
            <select value={String(v.status ?? "draft")}
                    onChange={(e) => set("status", e.target.value)}>
              <option value="draft">draft</option>
              <option value="approved">approved</option>
              <option value="rejected">rejected</option>
            </select>
          </div>
          <div className="form-row">
            <label>备注</label>
            <input value={String(v.comment ?? "")}
                   onChange={(e) => set("comment", e.target.value)} />
          </div>
          <div className="form-row">
            <label>实体速查</label>
            <div className="field-table">
              {form.entity_ids.map((id) => (
                <span key={id} className="text-xs text-muted">
                  <code>{id}</code>{form.entity_labels[id] ? ` · ${form.entity_labels[id]}` : ""}
                </span>
              ))}
            </div>
          </div>
          <div className="form-actions">
            <button type="button" className="ghost"
                    onClick={() => navigate(-1)}>取消</button>
            <button type="submit" className="primary">
              <Icon name="check" size={14} />保存
            </button>
          </div>
        </form>
      </div>
    </main>
  );
}
