/** 卡片动态表单（specs 驱动）：右栏新建/编辑共用。引用字段全部下拉，杜绝悬空引用。 */
import {useState} from "react";
import {api, ApiError} from "../api/client";
import type {FormSpec} from "../api/types";
import {Icon} from "./Icon";
import {toast} from "../state/toast";

export function CardForm({pid, kind, spec, isNew, cardId = "", onSaved, onCancel}: {
  pid: string;
  kind: string;
  spec: FormSpec;
  isNew: boolean;
  cardId?: string;
  onSaved: (id: string, bib: string | null) => void;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(spec.values);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const v = values;

  function set(name: string, value: unknown) {
    setValues({...v, [name]: value});
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setErrors({});
    try {
      if (isNew) {
        const resp = await api.post<{ok: boolean; id: string; bib: string | null}>(
          `/api/projects/${encodeURIComponent(pid)}/cards/${kind}`, v);
        toast.success(`已创建 ${resp.id}`);
        if (resp.bib) toast.info(`managed bib 已同步（${resp.bib}）`);
        onSaved(resp.id, resp.bib);
      } else {
        const resp = await api.patch<{ok: boolean; bib: string | null}>(
          `/api/projects/${encodeURIComponent(pid)}/cards/${kind}/${encodeURIComponent(cardId)}`, v);
        toast.success(`已保存 ${cardId}`);
        if (resp.bib) toast.info(`managed bib 已同步（${resp.bib}）`);
        onSaved(cardId, resp.bib);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.errors) setErrors(err.errors);
        toast.error(err.detail);
      } else {
        toast.error(String(err));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="form" onSubmit={submit}>
      {isNew && (
        <div className="form-row">
          <label>id（{spec.id_widget === "auto" ? "自动编号，可改" : spec.id_widget === "bibkey" ? "bib key" : "slug，手输"}）</label>
          {spec.id_widget === "bibkey" ? (
            <select value={String(v.id ?? "")} required
                    onChange={(e) => set("id", e.target.value)}>
              <option value="" disabled>选择 bib key…</option>
              {spec.id_choices.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          ) : (
            <input value={String(v.id ?? "")} placeholder={spec.prefilled_id}
                   onChange={(e) => set("id", e.target.value)} />
          )}
          {errors.id && <span className="form-error">{errors.id}</span>}
        </div>
      )}
      {spec.specs.map((s) => (
        <div className="form-row" key={s.name}>
          <label>{s.label}{s.required ? " *" : ""}</label>
          {s.widget === "textarea" && (
            <textarea rows={3} value={String(v[s.name] ?? "")}
                      onChange={(e) => set(s.name, e.target.value)} />
          )}
          {s.widget === "text" && (
            <input value={String(v[s.name] ?? "")}
                   onChange={(e) => set(s.name, e.target.value)} />
          )}
          {s.widget === "tags" && (
            <>
              <input list={`dl-${s.name}`} value={String(v[s.name] ?? "")}
                     placeholder="章节标签，逗号分隔" spellCheck={false}
                     onChange={(e) => set(s.name, e.target.value)} />
              <datalist id={`dl-${s.name}`}>
                {(spec.choices[s.choices ?? ""] ?? []).map((c) => (
                  <option key={c} value={c} />
                ))}
              </datalist>
            </>
          )}
          {s.widget === "yaml_map" && (
            <textarea rows={4} spellCheck={false}
                      value={String(v[s.name] ?? "")}
                      placeholder="key: value（YAML 映射）"
                      onChange={(e) => set(s.name, e.target.value)} />
          )}
          {s.widget === "select" && s.choices && (
            <select value={String(v[s.name] ?? "")} required={s.required}
                    onChange={(e) => set(s.name, e.target.value)}>
              <option value="" disabled>选择…</option>
              {(spec.choices[s.choices] ?? []).map((c) => (
                <option key={c} value={c}>
                  {spec.labels[s.choices ?? ""]?.[c]
                    ? `${c} · ${spec.labels[s.choices ?? ""]?.[c]}` : c}
                </option>
              ))}
            </select>
          )}
          {s.widget === "multiselect" && s.choices && (
            <div style={{display: "flex", flexWrap: "wrap", gap: 6}}>
              {(spec.choices[s.choices] ?? []).map((c) => {
                const list = Array.isArray(v[s.name]) ? v[s.name] as string[] : [];
                const checked = list.includes(c);
                return (
                  <label key={c} className="badge mono"
                         style={{cursor: "pointer",
                                 ...(checked ? {background: "var(--accent)", color: "var(--accent-fg)"} : {})}}>
                    <input type="checkbox" style={{display: "none"}} checked={checked}
                           onChange={() => set(s.name, checked
                             ? list.filter((x) => x !== c)
                             : [...list, c])} />
                    {spec.labels[s.choices ?? ""]?.[c]
                      ? `${c} · ${spec.labels[s.choices ?? ""]?.[c]}` : c}
                  </label>
                );
              })}
            </div>
          )}
          {errors[s.name] && <span className="form-error">{errors[s.name]}</span>}
        </div>
      ))}
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
        <label>备注（审阅意见）</label>
        <input value={String(v.comment ?? "")}
               onChange={(e) => set("comment", e.target.value)} />
      </div>
      <div className="form-actions">
        <button type="button" className="ghost" onClick={onCancel}>取消</button>
        <button type="submit" className="primary" disabled={saving}>
          <Icon name="check" size={14} />{saving ? "保存中…" : "保存"}
        </button>
      </div>
    </form>
  );
}
