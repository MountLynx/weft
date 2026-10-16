/** 卡片链路纯函数（webui-card-links 设计 §4.1）：邻接判定 / 邻居分组 / 计数 / 行筛选。
 * 统一规则：卡 a 连通卡 b ⟺ a 引用 b（a.links[b.kind] 含 b）或 b 引用 a
 * （a.referenced_by[复数(b.kind)] 含 b；referenced_by 记录在被引用方、键 = 引用方卡种复数）。
 * 悬空引用不在 entities，天然不连通。 */
import type {CardLinkEntity, CardLinks} from "../api/types";
import {KINDS} from "../components/kinds";

/** referenced_by 键 = 来源卡种复数；data/note 无出链字段，不做来源。 */
const PLURAL: Record<string, string> = {
  fact: "facts", claim: "claims", method: "methods", param: "params",
};

/** 引用字段 → 目标卡种（inspector chips 跳转用；data/note 无出链字段）。 */
export const FIELD_LINK_KINDS: Record<string, Record<string, string>> = {
  fact: {data: "data", supports: "claim"},
  claim: {cites: "note"},
  method: {derived_from: "note"},
  param: {method: "method", derived_from: "note"},
};

/** 卡 a 与卡 b 是否有边（任一方向；两参可为同一张卡时不保证有意义，调用方避开）。
 * 两个判据都是「bId 是否出现在 a 的邻接表」，aId 仅为调用点对称性保留。 */
export function linked(a: CardLinkEntity, _aId: string,
                       b: CardLinkEntity, bId: string): boolean {
  return (a.links[b.kind] ?? []).includes(bId)
      || (a.referenced_by[PLURAL[b.kind]] ?? []).includes(bId);
}

export interface NeighborGroup {kind: string; ids: string[]}

function entitiesOf(links: CardLinks): Record<string, CardLinkEntity> {
  return links.entities ?? {};
}

/** sel 卡的全部邻居按卡种分组（组按 KINDS 序、id 字母序；无邻居为空数组）。 */
export function neighborGroups(links: CardLinks, selId: string): NeighborGroup[] {
  const entities = entitiesOf(links);
  const sel = entities[selId];
  if (!sel) return [];
  const byKind = new Map<string, string[]>();
  for (const [tid, t] of Object.entries(entities)) {
    if (tid === selId || !linked(sel, selId, t, tid)) continue;
    const ids = byKind.get(t.kind) ?? [];
    ids.push(tid);
    byKind.set(t.kind, ids);
  }
  const order = (k: string) => {
    const i = (KINDS as readonly string[]).indexOf(k);
    return i === -1 ? 99 : i;
  };
  return [...byKind.entries()]
    .map(([kind, ids]) => ({kind, ids: [...ids].sort()}))
    .sort((x, y) => order(x.kind) - order(y.kind));
}

/** 当前卡种里连通 tag 的卡数（pill 计数徽章）。 */
export function linkedCount(links: CardLinks, curKind: string,
                            tagKind: string, tagId: string): number {
  const entities = entitiesOf(links);
  const tag = entities[tagId];
  // tagKind 与实体实际卡种不符按失效处理（fail-closed；noUnusedParameters 下 tagKind 必须参与判定）
  if (!tag || tag.kind !== tagKind) return 0;
  let n = 0;
  for (const [cid, c] of Object.entries(entities)) {
    if (c.kind === curKind && linked(c, cid, tag, tagId)) n += 1;
  }
  return n;
}

/** 行筛选：rowId 连通任一选中标签（"kind/id" 串）；标签或行失效按不匹配处理。 */
export function matchesAny(links: CardLinks, rowId: string, tags: string[]): boolean {
  const entities = entitiesOf(links);
  const row = entities[rowId];
  if (!row) return false;
  return tags.some((tag) => {
    const tagId = tag.slice(tag.indexOf("/") + 1);
    const tagEnt = entities[tagId];
    return tagEnt !== undefined && linked(row, rowId, tagEnt, tagId);
  });
}
