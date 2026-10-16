# WebUI 卡片链路筛选与跳转 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 卡片页全链路导航——侧栏「筛选」区以选中卡的邻居为标签（多选并集过滤当前列表），inspector 引用字段 chip 化跳转，后端新增实时 `/cards/links` 端点。

**Architecture:** 后端一个只读端点（`build_index` 实时反向边 + 正向链接字段按目标卡种合并）；前端一个 Workspace 级 Context（`CardsUiProvider`：links 数据 + 选中卡镜像 + 标签态）供 Sidebar 筛选区与 CardsPage 过滤共用；筛选纯前端计算。

**Tech Stack:** FastAPI（现有 app 内加路由）+ React 18 / react-router v6 / vitest + testing-library（现有 webui 脚手架）。

**设计文档:** `docs/superpowers/specs/2026-10-16-weft-webui-card-links-design.md`（决策 L1–L10）。

**测试计数（登记）:** pytest 基线 **812 passed, 2 deselected** → 目标 **817 passed, 2 deselected**（+5，新建 `tests/test_web_card_links.py`）；vitest 基线 **11 passed**（实测，AGENTS.md 的 8 已过时） → 目标 **15 passed**（+4，新建 `webui/src/CardFilter.test.tsx`）。

---

### Task 0: 执行环境（worktree + venv 重挂 + 前端依赖）

**Files:** 无代码变更（仅环境准备）。

- [ ] **Step 1: 创建 worktree 并进入**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git worktree add .worktrees/webui-card-links -b webui-card-links
cd .worktrees/webui-card-links
```

- [ ] **Step 2: 把 worktree 挂进主 venv（editable 安装指向 worktree 源码）**

主仓 `.venv` 是 editable 安装，默认指向主 checkout 的 `src/`；不重挂则 pytest 测的是主仓旧代码。

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pip install -e . -q
```

- [ ] **Step 3: 安装 webui 依赖（node_modules 不入库，worktree 需自装）**

```bash
cd webui && pnpm install && cd ..
```

- [ ] **Step 4: 基线自检**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests -q
```
Expected: `812 passed, 2 deselected`。

```bash
cd webui && pnpm test
```
Expected: `11 passed`。

---

### Task 1: 后端 `/api/projects/{pid}/cards/links` 端点（TDD）

**Files:**
- Create: `tests/test_web_card_links.py`
- Modify: `src/weft/web/api/cards.py`（imports 区 + `cards_overview` 与 `card_list` 之间）

- [ ] **Step 1: 写失败测试**

创建 `tests/test_web_card_links.py`：

```python
"""卡片链路端点 /cards/links（webui-card-links 设计 §2/§8）：实时反向索引 + 正向链接。"""
from tests.helpers import write_card
from tests.webutil import make_client


def test_card_links_payload(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "methods", "m-xt",
               {"id": "m-xt", "statement": "s", "protocol": "p",
                "derived_from": ["key2020"], "status": "approved"})
    write_card(root / "demo" / "metadata" / "params", "p-xt",
               {"id": "p-xt", "method": "m-xt", "values": {"rate": "5"},
                "derived_from": ["key2020"], "status": "draft"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert set(ents) == {"data-01", "fact-01", "claim-01", "key2020",
                         "m-xt", "p-xt"}
    assert ents["fact-01"]["links"] == {"data": ["data-01"],
                                        "claim": ["claim-01"]}
    assert ents["claim-01"]["links"] == {"note": []}
    assert ents["data-01"]["links"] == {}
    assert ents["fact-01"]["summary"] == "温度提高速率。"
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01"]
    assert ents["claim-01"]["referenced_by"]["facts"] == ["fact-01"]
    assert ents["m-xt"]["referenced_by"]["params"] == ["p-xt"]
    assert ents["key2020"]["referenced_by"]["methods"] == ["m-xt"]
    assert ents["key2020"]["referenced_by"]["params"] == ["p-xt"]
    assert ents["fact-01"]["referenced_by"]["nodes"] == ["para-01-01"]
    assert ents["p-xt"]["status"] == "draft"


def test_card_links_forward_keeps_dangling(tmp_path):
    # links 保留真实落盘内容（悬空引用可见）；反向索引按目标存在性过滤
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "facts", "fact-02",
               {"id": "fact-02", "data": ["data-01", "data-ghost"],
                "statement": "悬空引用。", "supports": ["claim-ghost"],
                "status": "draft"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert ents["fact-02"]["links"]["data"] == ["data-01", "data-ghost"]
    assert ents["fact-02"]["links"]["claim"] == ["claim-ghost"]
    assert "data-ghost" not in ents and "claim-ghost" not in ents
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01", "fact-02"]


def test_card_links_includes_rejected(tmp_path):
    client, root = make_client(tmp_path)
    write_card(root / "demo" / "metadata" / "facts", "fact-03",
               {"id": "fact-03", "data": ["data-01"], "statement": "被否决。",
                "supports": [], "status": "rejected"})
    ents = client.get("/api/projects/demo/cards/links").json()["entities"]
    assert ents["fact-03"]["status"] == "rejected"
    assert ents["data-01"]["referenced_by"]["facts"] == ["fact-01", "fact-03"]


def test_card_links_route_precedes_kind(tmp_path):
    # /cards/links 必须先于 /cards/{kind} 注册（决策 L2），否则被当卡种名 404
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/demo/cards/links").status_code == 200
    assert client.get("/api/projects/demo/cards/bogus").status_code == 404


def test_card_links_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.get("/api/projects/ghost/cards/links").status_code == 404
```

- [ ] **Step 2: 跑测试确认红**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests/test_web_card_links.py -v
```
Expected: 5 个用例全部 FAIL（404 not found 之类——路由不存在）。

- [ ] **Step 3: 实现端点**

`src/weft/web/api/cards.py` 两处修改。

imports 区（`from weft.engine.draft_rules import DraftError` 之后，保持字母序）加：

```python
from weft.graphgen.index import build_index
```

`cards_overview`（`@router.get("/projects/{pid}/cards")` 函数）之后、`card_list` 之前插入——**顺序不能颠倒**（决策 L2）：

```python
# 正向链接字段 → 目标卡种（值是真实落盘内容：悬空引用保留；反向边由 build_index 过滤）
_LINK_FIELDS: dict[str, dict[str, str]] = {
    "fact": {"data": "data", "supports": "claim"},
    "claim": {"cites": "note"},
    "method": {"derived_from": "note"},
    "param": {"method": "method", "derived_from": "note"},
}


@router.get("/projects/{pid}/cards/links")
def cards_links(request: Request, pid: str):
    """全量卡链路（webui-card-links 设计 §2）：实时反向索引 + 正向链接合并。

    只读、无落盘；rejected 卡包含（决策 L8）。路由先于 /cards/{kind}（决策 L2）。
    """
    entry = load_reviewable_or_404(request, pid)
    entities = build_index(entry.project)["entities"]
    for kind, fields in _LINK_FIELDS.items():
        for cid, card in getattr(entry.project, KIND_ATTRS[kind]).items():
            entities[cid]["links"] = {target: list(getattr(card, field))
                                      for field, target in fields.items()}
    for ent in entities.values():
        ent.setdefault("links", {})
    return {"entities": entities}
```

- [ ] **Step 4: 跑测试确认绿**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests/test_web_card_links.py -v
```
Expected: `5 passed`。

再跑全量确认零回归：

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests -q
```
Expected: `817 passed, 2 deselected`。

- [ ] **Step 5: 提交**

```bash
git add tests/test_web_card_links.py src/weft/web/api/cards.py
git commit -m "feat: WebUI 卡片链路端点 /cards/links——实时 build_index 反向边 + 正向链接按目标卡种合并"
```

---

### Task 2: 前端契约与共享态基建（无 UI 变化）

**Files:**
- Modify: `webui/src/api/types.ts`（文件末尾追加）
- Create: `webui/src/state/cardLinks.ts`
- Create: `webui/src/state/cardsUi.tsx`
- Modify: `webui/src/App.tsx:24-39`（Workspace 内挂 Provider）

- [ ] **Step 1: 契约类型**

`webui/src/api/types.ts` 末尾追加：

```typescript
export interface CardLinkEntity {
  kind: string;
  status: string;
  summary: string;
  links: Record<string, string[]>;
  referenced_by: Record<string, string[]>;
}

export interface CardLinks {
  entities: Record<string, CardLinkEntity>;
}
```

- [ ] **Step 2: 链路纯函数模块**

创建 `webui/src/state/cardLinks.ts`：

```ts
/** 卡片链路纯函数（webui-card-links 设计 §4.1）：邻接判定 / 邻居分组 / 计数 / 行筛选。
 * 统一规则：卡 a 连通卡 b ⟺ a 引用 b（a.links[b.kind] 含 b）或 b 引用 a
 * （b.referenced_by[复数(b.kind)] 含 a）。悬空引用不在 entities，天然不连通。 */
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

/** 卡 a 与卡 b 是否有边（任一方向；两参可为同一张卡时不保证有意义，调用方避开）。 */
export function linked(a: CardLinkEntity, aId: string,
                       b: CardLinkEntity, bId: string): boolean {
  return (a.links[b.kind] ?? []).includes(bId)
      || (b.referenced_by[PLURAL[b.kind]] ?? []).includes(aId);
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
  if (!tag) return 0;
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
```

- [ ] **Step 3: 共享态 Provider**

创建 `webui/src/state/cardsUi.tsx`：

```tsx
/** 卡片页共享 UI 态（webui-card-links 设计 §3）：/cards/links 数据 + 选中卡镜像 +
 * 筛选标签。Sidebar 筛选区与 CardsPage 过滤共用；仅 /cards/* 路由激活请求。 */
import {createContext, useCallback, useContext, useEffect, useMemo, useRef,
        useState} from "react";
import {useLocation} from "react-router-dom";
import {useApi} from "../hooks/useApi";
import type {CardLinks} from "../api/types";

export interface SelInfo {kind: string; id: string}

interface CardsUiValue {
  links: CardLinks | null;
  sel: SelInfo | null;
  reportSel: (key: string) => void;
  tags: string[];
  toggleTag: (tag: string) => void;
  clearTags: () => void;
}

const noop = () => {};
const CardsUiContext = createContext<CardsUiValue>({
  links: null, sel: null, reportSel: noop, tags: [], toggleTag: noop,
  clearTags: noop,
});

export function useCardsUi(): CardsUiValue {
  return useContext(CardsUiContext);
}

export function CardsUiProvider({pid, children}: {
  pid: string;
  children: React.ReactNode;
}) {
  const {pathname} = useLocation();
  const onCards = pathname.startsWith(`/p/${encodeURIComponent(pid)}/cards`);
  const {data} = useApi<CardLinks>(onCards
    ? `/api/projects/${encodeURIComponent(pid)}/cards/links` : null);
  // 载荷畸形（entities 缺失）按无数据降级：筛选区隐藏、过滤不生效
  const links = data !== null && data.entities !== undefined ? data : null;
  const [selKey, setSelKey] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  const reportSel = useCallback((key: string) => {
    setSelKey((prev) => (prev === key ? prev : key));
  }, []);
  const toggleTag = useCallback((tag: string) => {
    setTags((prev) => prev.includes(tag)
      ? prev.filter((t) => t !== tag) : [...prev, tag]);
  }, []);
  const clearTags = useCallback(() => setTags([]), []);

  // 换选中卡即清空标签（设计 §4.4 规则 1）；links 换代（项目切换/重载）同样清空
  const prevSel = useRef(selKey);
  useEffect(() => {
    if (prevSel.current !== selKey) {
      prevSel.current = selKey;
      setTags([]);
    }
  }, [selKey]);
  const prevLinks = useRef(links);
  useEffect(() => {
    if (prevLinks.current !== links) {
      prevLinks.current = links;
      setTags([]);
    }
  }, [links]);

  const sel = useMemo<SelInfo | null>(() => {
    if (!selKey) return null;
    const slash = selKey.indexOf("/");
    return {kind: selKey.slice(0, slash), id: selKey.slice(slash + 1)};
  }, [selKey]);

  const value = useMemo<CardsUiValue>(
    () => ({links, sel, reportSel, tags, toggleTag, clearTags}),
    [links, sel, reportSel, tags, toggleTag, clearTags]);

  return <CardsUiContext.Provider value={value}>{children}</CardsUiContext.Provider>;
}
```

- [ ] **Step 4: Workspace 挂 Provider**

`webui/src/App.tsx`：import 区加 `import {CardsUiProvider} from "./state/cardsUi";`；`Workspace` 组件改为：

```tsx
function Workspace({children}: {children: React.ReactNode}) {
  const {pid = ""} = useParams();
  const {data: dash} = useApi<Dashboard>(
    `/api/projects/${encodeURIComponent(pid)}`);
  return (
    <div className="app">
      <Topbar />
      <div className="workspace">
        <CardsUiProvider pid={pid}>
          <Sidebar dash={dash} />
          {children}
        </CardsUiProvider>
      </div>
      <StatusBar dash={dash} />
      <ToastHost />
    </div>
  );
}
```

- [ ] **Step 5: 构建与既有测试确认零回归**

```bash
cd webui && pnpm build && pnpm test && cd ..
```
Expected: build 成功；`11 passed`（基建 inert：无消费方，Provider 空转）。

- [ ] **Step 6: 提交**

```bash
git add webui/src/api/types.ts webui/src/state/cardLinks.ts webui/src/state/cardsUi.tsx webui/src/App.tsx src/weft/web/static/app
git commit -m "feat: WebUI 卡片链路共享态基建——types + 邻接纯函数 + CardsUiProvider（Workspace 级）"
```

---

### Task 3: 前端行为测试先红（4 用例，不提交红测试）

**Files:**
- Create: `webui/src/CardFilter.test.tsx`

- [ ] **Step 1: 写 4 个行为用例（引用尚不存在的 UI 类名，预期失败）**

创建 `webui/src/CardFilter.test.tsx`：

```tsx
/** 卡片链路筛选/跳转冒烟（webui-card-links 设计 §8）：pills、多选并集、换卡清空、筛选条与悬空 chip。 */
import {describe, expect, it, vi, afterEach} from "vitest";
import {render, screen, waitFor, fireEvent} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), {status: 200,
    headers: {"Content-Type": "application/json"}});
}

const counts = {data: 2, fact: 3, claim: 1, note: 0, method: 0, param: 0};
const dash = {n_parts: 0, n_cards: 6, n_errors: 0, n_warnings: 0,
              kind_counts: counts, review_queue: []};
const rb = {facts: [], claims: [], methods: [], params: [], nodes: []};
const linksPayload = {entities: {
  "data-01": {kind: "data", status: "approved", summary: "速率数据", links: {},
              referenced_by: {...rb, facts: ["fact-01", "fact-03"]}},
  "data-02": {kind: "data", status: "draft", summary: "", links: {},
              referenced_by: {...rb, facts: ["fact-02"]}},
  "fact-01": {kind: "fact", status: "draft", summary: "温度提高速率。",
              links: {data: ["data-01"], claim: ["claim-01"]},
              referenced_by: {...rb, nodes: ["para-01-01"]}},
  "fact-02": {kind: "fact", status: "draft", summary: "",
              links: {data: ["data-02"], claim: []}, referenced_by: {...rb}},
  "fact-03": {kind: "fact", status: "draft", summary: "",
              links: {data: ["data-01", "data-ghost"], claim: []},
              referenced_by: {...rb}},
  "claim-01": {kind: "claim", status: "approved", summary: "温度有正效应。",
               links: {note: []}, referenced_by: {...rb, facts: ["fact-01"]}},
}};

const factDetail = (id: string, data: string[]) => ({
  kind: "fact", label: "fact 卡", id, status: "draft", comment: "",
  rel: `metadata/facts/${id}.md`,
  fields: {data, statement: "…", supports: []},
  fixable: false, bib_managed: false});

function cardHandlers() {
  return {
    "/api/projects/demo": () => dash,
    "/api/projects/demo/cards/links": () => linksPayload,
    "/api/projects/demo/cards/fact": () => ({
      kind: "fact", label: "fact 卡", counts,
      rows: ["fact-01", "fact-02", "fact-03"].map((id) => ({
        id, status: "draft", key: "", rel: `metadata/facts/${id}.md`}))}),
    "/api/projects/demo/cards/data": () => ({
      kind: "data", label: "data 卡", counts,
      rows: [{id: "data-01", status: "approved", key: "速率数据",
              rel: "metadata/data/data-01.md"}]}),
    "/api/projects/demo/cards/fact/fact-01": () => factDetail("fact-01", ["data-01"]),
    "/api/projects/demo/cards/fact/fact-02": () => factDetail("fact-02", ["data-02"]),
    "/api/projects/demo/cards/fact/fact-03": () =>
      factDetail("fact-03", ["data-01", "data-ghost"]),
    "/api/projects/demo/cards/data/data-01": () => ({
      kind: "data", label: "data 卡", id: "data-01", status: "approved",
      comment: "", rel: "metadata/data/data-01.md",
      fields: {refs: [], source: "", description: "速率数据"},
      fixable: false, bib_managed: false}),
  };
}

async function renderCards(path = "/p/demo/cards/fact/fact-01") {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const h = cardHandlers()[url] as (() => unknown) | undefined;
    return jsonOk(h ? h() : {});
  }));
  const {default: App} = await import("./App");
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  await waitFor(() =>
    expect(document.querySelector(".right-panel")).not.toBeNull());
}

describe("侧栏筛选区（随选中卡的邻居标签）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("邻居按卡种分组为 pills，带计数徽章与摘要 title（KINDS 序）", async () => {
    await renderCards();
    await waitFor(() =>
      expect(document.querySelectorAll(".filter-panel .filter-group").length)
        .toBe(2));
    const kinds = [...document.querySelectorAll(".filter-panel .filter-kind")]
      .map((el) => el.textContent);
    expect(kinds).toEqual(["data", "claim"]);
    const pills = document.querySelectorAll(".filter-panel .tag-pill");
    expect(pills[0].textContent).toContain("data-01");
    expect(pills[0].querySelector(".tag-count")?.textContent).toBe("2");
    expect(pills[0].getAttribute("title")).toBe("速率数据");
    expect(pills[1].textContent).toContain("claim-01");
    expect(pills[1].querySelector(".tag-count")?.textContent).toBe("1");
    expect(screen.queryByText("筛选")).not.toBeNull();
  });

  it("多选并集过滤列表，再点取消、清除复原", async () => {
    await renderCards();
    const pills = () => [...document.querySelectorAll(".filter-panel .tag-pill")];
    await waitFor(() => expect(pills().length).toBe(2));
    fireEvent.click(pills()[1]);   // claim-01：仅 fact-01 支持它
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(1));
    fireEvent.click(pills()[0]);   // 并上 data-01 → {fact-01, fact-03}
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(2));
    expect(screen.queryByText("fact-02")).toBeNull();
    fireEvent.click(pills()[0]);   // 再点取消 → 仍剩 claim-01 一个标签
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(1));
    fireEvent.click(document.querySelector(".filter-head .filter-clear")
      as HTMLButtonElement);
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(3));
  });

  it("筛选激活时点其他行换选中卡：标签清空、过滤失效、pills 随新卡切换", async () => {
    await renderCards("/p/demo/cards/fact");
    await waitFor(() =>
      expect(document.querySelectorAll(".filter-panel .tag-pill").length).toBe(2));
    fireEvent.click(document.querySelectorAll(".filter-panel .tag-pill")[0]);
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(2));
    const rows = [...document.querySelectorAll(".row-list .row-item")];
    fireEvent.click(rows.find((r) => r.textContent?.includes("fact-03"))
      as HTMLElement);
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(3));
    expect(document.querySelector(".filter-bar")).toBeNull();
    // fact-03 的邻居只有 data-01（data-ghost 悬空不进 entities）
    await waitFor(() =>
      expect(document.querySelectorAll(".filter-panel .tag-pill").length).toBe(1));
  });
});

describe("筛选条与引用 chips", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("✕ 移除复原；chip 名跳转到那张卡；悬空引用 chip 警示", async () => {
    await renderCards();
    // 悬空：fact-03 的 data 含 data-ghost → inspector 一枚警示 chip
    fireEvent.click([...document.querySelectorAll(".row-list .row-item")]
      .find((r) => r.textContent?.includes("fact-03")) as HTMLElement);
    await waitFor(() =>
      expect(document.querySelectorAll(".right-panel .chip.dangling").length)
        .toBe(1));
    expect(document.querySelector(".right-panel .chip.dangling")
      ?.getAttribute("title")).toBe("悬空引用");
    // 筛选条 ✕ 移除
    fireEvent.click([...document.querySelectorAll(".filter-panel .tag-pill")]
      .find((p) => p.textContent?.includes("data-01")) as HTMLElement);
    await waitFor(() =>
      expect(document.querySelector(".filter-bar")).not.toBeNull());
    fireEvent.click(document.querySelector(".filter-bar .chip-x")
      as HTMLButtonElement);
    await waitFor(() =>
      expect(document.querySelector(".filter-bar")).toBeNull());
    // chip 名跳转：到 data-01 的 data 页
    fireEvent.click([...document.querySelectorAll(".filter-panel .tag-pill")]
      .find((p) => p.textContent?.includes("data-01")) as HTMLElement);
    await waitFor(() =>
      expect(document.querySelector(".filter-bar")).not.toBeNull());
    fireEvent.click(document.querySelector(".filter-bar .chip a") as HTMLElement);
    await waitFor(() => expect(
      (document.querySelector("a.nav-item.active") as HTMLAnchorElement)
        .getAttribute("href")).toBe("/p/demo/cards/data"));
  });
});
```

- [ ] **Step 2: 跑测试确认红**

```bash
cd webui && pnpm test
```
Expected: 4 个新用例 FAIL（`.filter-panel`/`.filter-bar`/`.chip.dangling` 均不存在），既有 11 个 PASS。

不提交（红测试不入库，Task 4/5 转绿后随实现一起提交）。

---

### Task 4: 侧栏筛选区 + CardsPage 过滤接线（测试 1–3 转绿）

**Files:**
- Create: `webui/src/components/CardFilterPanel.tsx`
- Modify: `webui/src/components/Sidebar.tsx`（import + `</nav>` 前挂载）
- Modify: `webui/src/pages/CardsPage.tsx`（imports、Context 接线、rows 过滤、筛选条）

- [ ] **Step 1: CardFilterPanel 组件**

创建 `webui/src/components/CardFilterPanel.tsx`：

```tsx
/** 侧栏「筛选」区（webui-card-links 设计 §4.1）：选中卡的邻居标签，多选并集过滤。
 * 非卡片路由 / 无 links / 无选中卡 / 无邻居时整区隐藏。 */
import {useLocation, useParams} from "react-router-dom";
import {useCardsUi} from "../state/cardsUi";
import {linkedCount, neighborGroups} from "../state/cardLinks";
import {Icon} from "./Icon";
import {KIND_ICONS} from "./kinds";

export function CardFilterPanel() {
  const {pid = "", kind = ""} = useParams();
  const {pathname} = useLocation();
  const base = `/p/${encodeURIComponent(pid)}`;
  const {links, sel, tags, toggleTag, clearTags} = useCardsUi();
  if (!pathname.startsWith(`${base}/cards`) || links === null || sel === null) {
    return null;
  }
  const groups = neighborGroups(links, sel.id);
  if (groups.length === 0) return null;
  return (
    <div className="filter-panel">
      <div className="filter-head">
        <span className="section-label">筛选</span>
        {tags.length > 0 && (
          <button className="filter-clear" onClick={clearTags}>清除</button>
        )}
      </div>
      {groups.map((g) => (
        <div key={g.kind} className="filter-group">
          <div className="filter-kind">
            <Icon name={KIND_ICONS[g.kind] ?? "file-text"} size={12} />
            {g.kind}
          </div>
          <div className="filter-tags">
            {g.ids.map((id) => {
              const ent = links.entities[id];
              const tag = `${g.kind}/${id}`;
              return (
                <button key={id}
                        className={`tag-pill${tags.includes(tag) ? " active" : ""}`}
                        title={ent.summary || id}
                        onClick={() => toggleTag(tag)}>
                  <span className="truncate">{id}</span>
                  <span className="tag-count">
                    {linkedCount(links, kind, g.kind, id)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Sidebar 挂载**

`webui/src/components/Sidebar.tsx`：import 区加 `import {CardFilterPanel} from "./CardFilterPanel";`；`</nav>` 闭合前（诊断 NavLink 之后）加一行：

```tsx
      <CardFilterPanel />
```

- [ ] **Step 3: CardsPage 接线**

`webui/src/pages/CardsPage.tsx` 三处修改。

（a）imports 区加：

```tsx
import {FIELD_LINK_KINDS, matchesAny} from "../state/cardLinks";
import {useCardsUi} from "../state/cardsUi";
```

（b）`CardsPage()` 组件内，`const rows = data?.rows ?? [];` 一行替换为：

```tsx
  const {links, tags, reportSel, toggleTag, clearTags} = useCardsUi();
  const allRows = data?.rows ?? [];
  // 多选并集过滤（设计 §4.1）：选中卡连通自己的每个邻居，恒在结果集，无空态分支
  const rows = tags.length === 0 ? allRows
    : allRows.filter((r) => links !== null && matchesAny(links, r.id, tags));

  // 选中卡镜像上报（侧栏筛选区数据源；换卡清空标签在 Provider 内完成）
  useEffect(() => {
    reportSel(sel ? `${sel.kind}/${sel.id}` : "");
  }, [sel, reportSel]);
  useEffect(() => () => reportSel(""), []);   // 离开卡片页清镜像
```

注意：`useEffect` 已在文件 imports 中。该块必须放在现有渲染期同步校正代码之后、`if (!effectiveKind)` 早退之前（hooks 不能条件跳过）。

（c）列表渲染改用过滤后的 rows，并在 `page-body` 顶部插入筛选条。`page-body` div 整块改为：

```tsx
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
                    <a href="#"
                       onClick={(e) => {
                         e.preventDefault();
                         navigate(`/p/${encodeURIComponent(pid)}/cards/${tagKind}/${encodeURIComponent(tagId)}`);
                       }}>{tagId}</a>
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
```

（此块与原代码的差异仅两处：顶部多筛选条条件渲染；`{(data?.rows ?? []).map(...)` 改为 `{rows.map(...)`。其余原样保留。）

- [ ] **Step 4: 跑测试确认 1–3 绿（测试 4 仍红——inspector chips 在 Task 5）**

```bash
cd webui && pnpm test
```
Expected: 14 passed, 1 failed（失败的是「筛选条与引用 chips」用例——`.chip.dangling` 尚不存在）。

既有 11 个用例必须全绿（回归门）。

- [ ] **Step 5: 提交**

```bash
git add webui/src/components/CardFilterPanel.tsx webui/src/components/Sidebar.tsx webui/src/pages/CardsPage.tsx
git commit -m "feat: WebUI 侧栏筛选区随选中卡列邻居标签——多选并集过滤 + 筛选条（✕ 移除/chip 名跳转）"
```

---

### Task 5: Inspector 引用字段 chips（测试 4 转绿）

**Files:**
- Modify: `webui/src/pages/CardsPage.tsx`（`CardInspector` 的 field-table 渲染）

- [ ] **Step 1: field-table 值按链接字段渲染 chips**

`CardInspector` 组件内：函数体开头（`const navigate = useNavigate();` 之后）加：

```tsx
  const {links} = useCardsUi();
```

field-table 一块替换为：

```tsx
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
                    {refs.length === 0 ? "—" : refs.map((ref) => {
                      const target = links?.entities[ref];
                      const dangling = links !== null && target === undefined;
                      return (
                        <a key={ref}
                           className={`chip${dangling ? " dangling" : ""}`}
                           title={dangling ? "悬空引用" : (target?.summary || ref)}
                           onClick={() => navigate(
                             `/p/${encodeURIComponent(pid)}/cards/${linkKind}/${encodeURIComponent(ref)}`)}>
                          {ref}
                        </a>
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
```

（语义：`data`/`supports`/`cites`/`method`/`derived_from` 值变可点 chip，跳目标卡种页；悬空引用警示色 + title（决策 L9）；`refs`（图号）与其余字段维持原样。）

- [ ] **Step 2: 跑测试确认全绿**

```bash
cd webui && pnpm test
```
Expected: `15 passed`。

- [ ] **Step 3: 提交**

```bash
git add webui/src/pages/CardsPage.tsx
git commit -m "feat: WebUI inspector 引用字段 chip 化——跨卡种跳转 + 悬空引用警示色"
```

---

### Task 6: 样式 + 构建产物入库

**Files:**
- Modify: `src/weft/web/static/webui.css`（末尾追加）
- Modify: `src/weft/web/static/app/**`（构建产物，命令生成）

- [ ] **Step 1: webui.css 末尾追加（全部走令牌，themes/*.css 不动）**

```css
/* ---- 卡片链路：侧栏筛选区 + 筛选条 + 引用 chip（webui-card-links 设计 §5）---- */
.sidebar .filter-panel {
  border-top: 1px solid var(--border);
  margin-top: 8px;
  padding: 10px 12px 14px;
  max-height: 40vh;
  overflow-y: auto;
}
.filter-head { display: flex; align-items: center; justify-content: space-between; }
.filter-head .section-label { margin: 0; }
.filter-clear {
  height: auto; padding: 0; border: none; background: none;
  color: var(--text-muted); font-size: var(--fs-xs); cursor: pointer;
}
.filter-clear:hover { color: var(--text-heading); text-decoration: underline; }
.filter-group { margin-top: 8px; }
.filter-kind {
  display: flex; align-items: center; gap: 4px;
  font-size: var(--fs-xs); color: var(--text-muted); margin-bottom: 4px;
}
.filter-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag-pill {
  display: inline-flex; align-items: center; gap: 5px; max-width: 100%;
  height: auto; padding: 2px 8px;
  border: 1px solid var(--border); border-radius: var(--r-full);
  background: var(--surface); color: var(--text);
  font-size: var(--fs-xs); cursor: pointer;
}
.tag-pill:hover { border-color: var(--border-strong); background: var(--surface-hover); }
.tag-pill.active { background: var(--accent); border-color: var(--accent); color: var(--accent-fg); }
.tag-pill .truncate { max-width: 110px; }
.tag-count { font-size: 10px; color: var(--text-secondary); }
.tag-pill.active .tag-count { color: var(--accent-fg); opacity: 0.75; }
.filter-bar {
  display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
  padding: 6px 10px; margin-bottom: 10px;
  border: 1px solid var(--border); border-radius: var(--r-md);
  font-size: var(--fs-sm);
}
.filter-bar .label { color: var(--text-muted); }
.chip {
  display: inline-flex; align-items: center; gap: 4px;
  height: auto; padding: 1px 8px;
  border: 1px solid var(--border); border-radius: var(--r-full);
  background: var(--surface); color: var(--text);
  font-size: var(--fs-xs); cursor: pointer;
}
a.chip { text-decoration: none; }
a.chip:hover { border-color: var(--border-strong); background: var(--surface-hover); }
.chip.dangling { color: var(--warning); border-color: var(--warning); }
.chip-x {
  height: auto; padding: 0; border: none; background: none;
  color: var(--text-muted); cursor: pointer; font-size: var(--fs-xs);
}
.chip-x:hover { color: var(--text-heading); }
```

- [ ] **Step 2: 构建产物入库（wheel 分发 + 离线可运行，工作流约定）**

```bash
cd webui && pnpm build && cd ..
```
Expected: 构建成功，产物更新 `src/weft/web/static/app/`。

- [ ] **Step 3: 提交**

```bash
git add src/weft/web/static/webui.css src/weft/web/static/app
git commit -m "feat: WebUI 卡片链路样式（筛选区/筛选条/引用 chip 走令牌）+ 构建产物入库"
```

---

### Task 7: 全量回归 + 合回 main

- [ ] **Step 1: 双侧全量回归**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests -q
```
Expected: `817 passed, 2 deselected`。

```bash
cd webui && pnpm test && cd ..
```
Expected: `15 passed`。

- [ ] **Step 2: 浏览器手动冒烟（examples/paper-demo）**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/weft.exe" serve --projects-root examples
```
浏览器开 `http://127.0.0.1:8000/p/paper-demo/cards/fact`：侧栏出现「筛选」区（data/claim 两组 pills）；点 data-01 pill 列表收窄；筛选条 chip 名跳转 data 页；data 页 pills 显示 fact 组；inspector `data`/`supports` 值为可点 chip。冒烟产生的 `examples/paper-demo/drafts/` 若有产物用完即删（工作区约定）。

- [ ] **Step 3: 合回 main 并清理（工作区约定：完成后删 worktree/分支）**

```bash
cd "C:/Users/xingy/Desktop/开发/weft"
git merge --no-ff webui-card-links -m "feat: WebUI 卡片链路筛选与跳转——侧栏随选标签过滤 + 引用字段 chip 跳转 + /cards/links 端点"
git branch -d webui-card-links
git worktree remove .worktrees/webui-card-links
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pip install -e . -q
```

- [ ] **Step 4: main 上最终验证 + 推送**

```bash
"C:/Users/xingy/Desktop/开发/weft/.venv/Scripts/python.exe" -m pytest tests -q
git push
```
Expected: `817 passed, 2 deselected`；push 到 origin/main 成功。
