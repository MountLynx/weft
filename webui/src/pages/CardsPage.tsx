/** 卡片列表 + 右栏 inspector（详情/审阅/改名/一键修复/内联新建与编辑）。卡种导航只在侧栏，无页签。 */
import {useEffect, useState} from "react";
import {Link, Navigate, useNavigate, useParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {CardDetail, CardsList, FormSpec} from "../api/types";
import {useApi} from "../hooks/useApi";
import {CardForm} from "../components/CardForm";
import {Icon} from "../components/Icon";
import {KINDS, kindIcon} from "../components/kinds";
import {StatusBadge} from "../components/StatusBadge";
import {FIELD_LINK_KINDS, matchesAny} from "../state/cardLinks";
import {useCardsUi} from "../state/cardsUi";
import {toast} from "../state/toast";

/** 右栏模式（组件态，不入 URL；kind 切换即失效回落 view，D1/D6）。 */
type PanelMode =
  | {type: "view"}
  | {type: "new"; kind: string}
  | {type: "edit"; kind: string; id: string};

function CardInspector({pid, kind, cardId, onEdit, onChanged}: {
  pid: string;
  kind: string;
  cardId: string;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const navigate = useNavigate();
  const {links} = useCardsUi();
  const {data: card, reload} = useApi<CardDetail>(
    `/api/projects/${encodeURIComponent(pid)}/cards/${kind}/${encodeURIComponent(cardId)}`);
  const [comment, setComment] = useState("");
  const [renaming, setRenaming] = useState(false);
  const [newId, setNewId] = useState("");
  const [fixing, setFixing] = useState(false);

  useEffect(() => {
    setComment("");
    setRenaming(false);
  }, [cardId]);

  async function review(status: string) {
    try {
      const resp = await api.post<{ok: boolean; bib: string | null}>(
        `/api/projects/${encodeURIComponent(pid)}/cards/${kind}/${encodeURIComponent(cardId)}/status`,
        {status, comment});
      toast.success(`已${status === "approved" ? "批准" : status === "rejected" ? "否决" : "退回 draft"}：${cardId}`);
      if (resp.bib) toast.info(`managed bib 已同步（${resp.bib}）`);
      reload();
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function rename(e: React.FormEvent) {
    e.preventDefault();
    try {
      const resp = await api.post<{ok: boolean; id: string}>(
        `/api/projects/${encodeURIComponent(pid)}/cards/${kind}/${encodeURIComponent(cardId)}/rename`,
        {new_id: newId});
      toast.success(`已改名：${resp.id}`);
      navigate(`/p/${encodeURIComponent(pid)}/cards/${kind}/${resp.id}`);
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    }
  }

  async function fix() {
    setFixing(true);
    try {
      const resp = await api.post<{ok: boolean; result: string}>(
        `/api/projects/${encodeURIComponent(pid)}/bib/fix/${encodeURIComponent(cardId)}`);
      if (resp.result === "added") toast.success("条目已追加进 bib");
      else if (resp.result === "present") toast.info("bib 中已有该 key");
      else toast.error("修复失败（bib 不可写或形状非法）");
      reload();
      onChanged();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
    } finally {
      setFixing(false);
    }
  }

  if (!card) return null;
  return (
    <aside className="right-panel">
      <div className="panel-head">
        <Icon name={kindIcon(kind)} size={15} />
        <strong style={{fontSize: "var(--fs-sm)"}} className="truncate">{card.id}</strong>
        <StatusBadge status={card.status} />
        <span className="spacer" style={{flex: 1}} />
        <button className="icon-btn" title="编辑" onClick={onEdit}>
          <Icon name="pencil" size={14} />
        </button>
      </div>
      <div className="panel-body">
        <div className="field-table">
          {Object.entries(card.fields).map(([k, v]) => {
            const linkKind = FIELD_LINK_KINDS[kind]?.[k];
            const raw = v as unknown;
            const refs: string[] = linkKind
              ? (Array.isArray(raw) ? raw.map(String) : raw ? [String(raw)] : [])
              : [];
            return (
              <div className="field" key={k}>
                <span className="k">{k}</span>
                {linkKind ? (
                  <span className="v">
                    {refs.length === 0 ? "—" : refs.map((ref, i) => {
                      const target = links?.entities[ref];
                      const dangling = links !== null && target === undefined;
                      return (
                        <Link key={`${ref}-${i}`}
                              className={`chip${dangling ? " dangling" : ""}`}
                              title={dangling ? "悬空引用" : (target?.summary || ref)}
                              to={`/p/${encodeURIComponent(pid)}/cards/${linkKind}/${encodeURIComponent(ref)}`}>
                          {ref}
                        </Link>
                      );
                    })}
                  </span>
                ) : (
                  <span className={`v${k === "entry" ? " mono" : ""}`}>{v || "—"}</span>
                )}
              </div>
            );
          })}
        </div>
        {card.fixable && (
          <div className="banner warning">
            <div>note id 不在 bib 中（E-NOTE-NOT-IN-BIB）</div>
            <button className="primary" onClick={fix} disabled={fixing}>
              <Icon name="wrench" size={13} />一键修复：追加进 bib
            </button>
          </div>
        )}
        <div className="form-row">
          <label>审阅备注</label>
          <textarea rows={2} value={comment} placeholder="可选"
                    onChange={(e) => setComment(e.target.value)} />
        </div>
        <div style={{display: "flex", gap: 6}}>
          <button className="primary" style={{flex: 1}} onClick={() => review("approved")}>
            <Icon name="check" size={14} />批准
          </button>
          <button className="danger" style={{flex: 1}} onClick={() => review("rejected")}>
            <Icon name="x" size={14} />否决
          </button>
          <button onClick={() => review("draft")}>↩ 退回</button>
        </div>
        {renaming ? (
          <form className="form-row" onSubmit={rename}>
            <label>新 id（bib key / slug）</label>
            <div className="row-inline">
              <input autoFocus value={newId} onChange={(e) => setNewId(e.target.value)} />
              <button type="submit" className="primary">确定</button>
              <button type="button" className="ghost" onClick={() => setRenaming(false)}>
                取消
              </button>
            </div>
          </form>
        ) : (
          <button className="ghost" onClick={() => { setRenaming(true); setNewId(cardId); }}>
            <Icon name="pencil" size={13} />改名
          </button>
        )}
        <div className="text-xs text-muted">{card.rel}</div>
      </div>
    </aside>
  );
}

/** 右栏编辑面板：specs 驱动表单（保存/取消均留在卡片页）。 */
function CardEditPanel({pid, kind, cardId, onClose, onSaved}: {
  pid: string;
  kind: string;
  cardId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const {data: spec} = useApi<FormSpec>(
    `/api/projects/${encodeURIComponent(pid)}/cards/${kind}/${encodeURIComponent(cardId)}/edit`);
  return (
    <aside className="right-panel">
      <div className="panel-head">
        <Icon name={kindIcon(kind)} size={15} />
        <strong style={{fontSize: "var(--fs-sm)"}} className="truncate">编辑 {cardId}</strong>
        <span className="spacer" style={{flex: 1}} />
        <button className="icon-btn" title="关闭" onClick={onClose}>
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="panel-body">
        {spec && (
          <CardForm key={cardId} pid={pid} kind={kind} spec={spec} isNew={false}
                    cardId={cardId} onSaved={onSaved} onCancel={onClose} />
        )}
      </div>
    </aside>
  );
}

/** 右栏新建面板：保存后选中新卡并刷新列表。 */
function NewCardPanel({pid, kind, onClose, onCreated}: {
  pid: string;
  kind: string;
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const {data: spec} = useApi<FormSpec>(
    `/api/projects/${encodeURIComponent(pid)}/card-forms/${kind}`);
  return (
    <aside className="right-panel">
      <div className="panel-head">
        <Icon name={kindIcon(kind)} size={15} />
        <strong style={{fontSize: "var(--fs-sm)"}} className="truncate">
          新建 {spec?.label ?? kind}
        </strong>
        <span className="spacer" style={{flex: 1}} />
        <button className="icon-btn" title="关闭" onClick={onClose}>
          <Icon name="x" size={14} />
        </button>
      </div>
      <div className="panel-body">
        {spec && (
          <CardForm key={kind} pid={pid} kind={kind} spec={spec} isNew={true}
                    onSaved={(id) => onCreated(id)} onCancel={onClose} />
        )}
      </div>
    </aside>
  );
}

export function CardsPage() {
  const {pid = "", kind = "", cardId: routeCardId} = useParams();
  const navigate = useNavigate();
  const effectiveKind = KINDS.includes(kind as never) ? kind : "";
  const routeSel = routeCardId ? {kind: effectiveKind, id: routeCardId} : null;
  const [sel, setSel] = useState<{kind: string; id: string} | null>(routeSel);
  const [mode, setMode] = useState<PanelMode>({type: "view"});
  const {data, loading, reload: reloadList} = useApi<CardsList>(
    effectiveKind
      ? `/api/projects/${encodeURIComponent(pid)}/cards/${effectiveKind}`
      : `/api/projects/${encodeURIComponent(pid)}/cards`);
  const {links, tags, reportSel, toggleTag, clearTags, reloadLinks} = useCardsUi();
  const allRows = data?.rows ?? [];
  // 多选并集过滤（设计 §4.1）：选中卡连通自己的每个邻居，恒在结果集，无空态分支
  const rows = tags.length === 0 || links === null ? allRows
    : allRows.filter((r) => matchesAny(links, r.id, tags));

  // 选中卡镜像上报（侧栏筛选区数据源；换卡清空标签在 Provider 内完成）
  useEffect(() => {
    reportSel(sel ? `${sel.kind}/${sel.id}` : "");
  }, [sel, reportSel]);
  useEffect(() => () => reportSel(""), []);   // 离开卡片页清镜像

  // 渲染期同步校正（React adjusting-state-during-render 范式）：
  // kind 切换/路由直达新卡立即作废旧选中——跨卡种窗口绝不渲染 inspector、不发 404 详情请求
  if (sel && (sel.kind !== effectiveKind || (routeSel && sel.id !== routeSel.id))) {
    setSel(routeSel);
  } else if (!sel && effectiveKind && rows.length > 0) {
    setSel({kind: effectiveKind, id: rows[0].id});   // 默认选中第一张
  }
  // mode 同帧失效：卡种切换后 new/edit 模式不再成立，回落查看态（D6）
  const activeMode: PanelMode =
    mode.type !== "view" && mode.kind !== effectiveKind ? {type: "view"} : mode;

  // inspector 只对「当前卡种列表里真实存在」的选中项渲染（总览队列直达详情也走这条）
  const validSelected = sel && sel.kind === effectiveKind
    && rows.some((r) => r.id === sel.id) ? sel.id : "";

  const counts = data?.counts ?? {};
  const creating = activeMode.type === "new";
  const editing = activeMode.type === "edit" && validSelected !== ""
    && activeMode.id === validSelected;

  function startView() {
    setMode({type: "view"});
  }

  function openCreate() {
    setMode({type: "new", kind: effectiveKind});
  }

  function selectRow(id: string) {
    startView();
    setSel({kind: effectiveKind, id});
    navigate(`/p/${encodeURIComponent(pid)}/cards/${effectiveKind}/${encodeURIComponent(id)}`);
  }

  // 无 kind 落地（/cards）：卡种导航只保留侧栏一处，等 counts 到手后
  // 直接落到首个非空卡种（全空则 data），不渲染任何页签。
  if (!effectiveKind) {
    if (loading) return <main className="center" />;
    const target = KINDS.find((k) => (counts[k] ?? 0) > 0) ?? "data";
    return <Navigate to={`/p/${encodeURIComponent(pid)}/cards/${target}`} replace />;
  }

  return (
    <>
      <main className="center">
        <div className="page-head">
          <h2>{data?.label ?? "卡片"}</h2>
          <span className="spacer" />
          <button className="btn" style={{display: "inline-flex", alignItems: "center", gap: 6}}
                  onClick={openCreate}>
            <Icon name="plus" size={14} />新建
          </button>
          {effectiveKind === "note" && (
            <button onClick={() => navigate(`/p/${encodeURIComponent(pid)}/inspire`)}>
              <Icon name="upload" size={14} />AI 提案文献
            </button>
          )}
        </div>
        <div className="page-body">
          {tags.length > 0 && (
            <div className="filter-bar">
              <span className="label">筛选：</span>
              {tags.map((tag) => {
                const slash = tag.indexOf("/");
                const tagKind = tag.slice(0, slash);
                const tagId = tag.slice(slash + 1);
                return (
                  <span key={tag} className="chip active">
                    <Link to={`/p/${encodeURIComponent(pid)}/cards/${tagKind}/${encodeURIComponent(tagId)}`}>{tagId}</Link>
                    <button className="chip-x" title="移除"
                            onClick={() => toggleTag(tag)}>×</button>
                  </span>
                );
              })}
              <button className="filter-clear" onClick={clearTags}>清除</button>
            </div>
          )}
          {(data?.rows ?? []).length === 0 ? (
            <div className="empty-state">
              <span className="big-icon"><Icon name={kindIcon(effectiveKind)} size={56} /></span>
              <div className="hint">还没有 {effectiveKind} 卡</div>
              <button className="btn primary" style={{display: "inline-flex", alignItems: "center", gap: 6}}
                      onClick={openCreate}>
                <Icon name="plus" size={14} />新建 {effectiveKind} 卡
              </button>
            </div>
          ) : (
            <div className="row-list">
              {rows.map((r) => (
                <a key={r.id}
                   className={`row-item${r.id === validSelected ? " selected" : ""}`}
                   onClick={(e) => {
                     e.preventDefault();
                     selectRow(r.id);
                   }}>
                  <Icon name={kindIcon(effectiveKind)} size={15} />
                  <div className="main">
                    <span className="title truncate">{r.id}</span>
                    {r.key && <span className="meta text-muted truncate">{r.key}</span>}
                  </div>
                  <span className="end"><StatusBadge status={r.status} /></span>
                </a>
              ))}
            </div>
          )}
        </div>
      </main>
      {creating ? (
        <NewCardPanel pid={pid} kind={effectiveKind} onClose={startView}
                      onCreated={(id) => {
                        startView();
                        reloadList();
                        reloadLinks();   // 新卡可能成为别卡的链接目标，防悬空误报
                        navigate(`/p/${encodeURIComponent(pid)}/cards/${effectiveKind}/${encodeURIComponent(id)}`);
                      }} />
      ) : validSelected ? (
        editing ? (
          <CardEditPanel pid={pid} kind={effectiveKind} cardId={validSelected}
                         onClose={startView}
                         onSaved={() => { startView(); reloadList(); reloadLinks(); }} />
        ) : (
          <CardInspector pid={pid} kind={effectiveKind} cardId={validSelected}
                         onEdit={() => setMode({type: "edit", kind: effectiveKind, id: validSelected})}
                         onChanged={() => navigate(0)} />
        )
      ) : null}
    </>
  );
}
