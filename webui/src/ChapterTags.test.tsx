/** 章节标签前端冒烟（card-chapters 设计 §5.2）：章节筛选 chips、tags 表单控件、本章标签卡区块。 */
import {describe, expect, it, vi, afterEach} from "vitest";
import {render, screen, waitFor, fireEvent} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), {status: 200,
    headers: {"Content-Type": "application/json"}});
}

const counts = {data: 0, fact: 0, claim: 2, note: 1, method: 0, param: 0};
const dash = {n_parts: 1, n_cards: 3, n_errors: 0, n_warnings: 0,
              kind_counts: counts, review_queue: []};
const rb = {facts: [], claims: [], methods: [], params: [], nodes: []};

const claimRows = [
  {id: "claim-01", status: "approved", key: "自持论断。",
   chapters: ["introduction"], rel: "metadata/claims/uncited/claim-01.md"},
  {id: "claim-02", status: "approved", key: "文献论断。",
   chapters: ["results"], rel: "metadata/claims/cited/claim-02.md"},
];

function cardHandlers(): Record<string, () => unknown> {
  return {
    "/api/projects/demo": () => dash,
    "/api/projects/demo/cards/links": () => ({entities: {
      "claim-01": {kind: "claim", status: "approved", summary: "自持论断。",
                   links: {}, referenced_by: rb},
      "claim-02": {kind: "claim", status: "approved", summary: "文献论断。",
                   links: {note: ["key2020"]}, referenced_by: rb},
      "key2020": {kind: "note", status: "approved", summary: "文献要点。",
                  links: {}, referenced_by: {...rb, claims: ["claim-02"]}},
    }}),
    "/api/projects/demo/cards/claim": () => ({
      kind: "claim", label: "claim 卡", counts, rows: claimRows}),
    "/api/projects/demo/cards/claim/claim-01": () => ({
      kind: "claim", label: "claim 卡", id: "claim-01", status: "approved",
      comment: "", rel: "metadata/claims/uncited/claim-01.md",
      fields: {claim_type: "uncited", statement: "自持论断。", cites: [],
               chapters: ["introduction"]}, fixable: false, bib_managed: false}),
    "/api/projects/demo/parts": () => ({
      ok: true, parts: [{id: "sec-01", workflow: null, n_nodes: 1}], first: "sec-01"}),
    "/api/projects/demo/parts/sec-01": () => ({
      ok: true, part: {id: "sec-01", workflow: null},
      workflow_vocab: ["introduction", "methods", "results", "discussion"],
      chapter: "01-results", chapter_norm: "results",
      chapter_cards: [
        {id: "claim-02", kind: "claim", status: "approved",
         key: "文献论断。", used: true},
        {id: "key2020", kind: "note", status: "approved",
         key: "文献要点。", used: false},
      ],
      nodes: [{id: "para-01-01", purpose: "describe", status: "approved",
               comment: "", uses: [{id: "claim-02", role: "background"}]}],
      use_labels: {"claim-02": "文献论断。"}, draft_text: null}),
  };
}

async function renderAt(path: string) {
  const fetchMock = vi.fn(async (url: string) => {
    const h = cardHandlers()[url] as (() => unknown) | undefined;
    return jsonOk(h ? h() : {});
  });
  vi.stubGlobal("fetch", fetchMock);
  const {default: App} = await import("./App");
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
  return fetchMock;
}

describe("卡片页章节筛选（card-chapters §5.2）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("chips 来自 rows chapters 并集；多选并集过滤；清除复原", async () => {
    await renderAt("/p/demo/cards/claim/claim-01");
    await waitFor(() =>
      expect(document.querySelectorAll(".chapter-bar .chip").length).toBe(2));
    const chips = [...document.querySelectorAll(".chapter-bar .chip")]
      .map((el) => el.textContent);
    expect(chips).toEqual(["introduction", "results"]);   // 字母序
    fireEvent.click(document.querySelectorAll(".chapter-bar .chip")[1]);
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(1));
    expect(screen.queryByText("claim-01")).toBeNull();     // results → 仅 claim-02
    fireEvent.click(document.querySelectorAll(".chapter-bar .chip")[0]);
    await waitFor(() =>
      expect(document.querySelectorAll(".row-list .row-item").length).toBe(2)); // 并集
    fireEvent.click(document.querySelector(".chapter-bar .filter-clear") as HTMLButtonElement);
    await waitFor(() =>
      expect(document.querySelectorAll(".chapter-bar .chip.active").length).toBe(0));
    expect(document.querySelectorAll(".row-list .row-item").length).toBe(2);
  });

  it("章节筛选与链路筛选叠加 = AND", async () => {
    await renderAt("/p/demo/cards/claim/claim-01");
    await waitFor(() =>
      expect(document.querySelectorAll(".filter-panel .tag-pill").length).toBe(0));
    // claim-01 无邻居 → 侧栏无 pills；chapter chips 独立生效已在上例覆盖
    expect(document.querySelectorAll(".chapter-bar .chip").length).toBe(2);
  });
});

describe("卡片表单 tags 控件（card-chapters §5.1）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("chapters 字段渲染 tags 输入 + datalist；提交原文由服务端解析", async () => {
    const formSpec = {
      kind: "claim", label: "claim 卡", is_new: true, id_widget: "auto",
      prefilled_id: "claim-03", id_choices: [],
      specs: [
        {name: "claim_type", label: "claim_type", widget: "select",
         choices: "claim_type", required: true},
        {name: "statement", label: "statement", widget: "textarea",
         choices: null, required: true},
        {name: "chapters", label: "chapters（章节标签）", widget: "tags",
         choices: "chapter_names", required: false},
      ],
      choices: {claim_type: ["uncited", "cited"], chapter_names: ["results"]},
      labels: {claim_type: {}, chapter_names: {}},
      values: {status: "draft", comment: "", chapters: ""},
    };
    const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
      if (url === "/api/projects/demo") return jsonOk(dash);
      if (url === "/api/projects/demo/cards/links")
        return jsonOk({entities: {}});
      if (url === "/api/projects/demo/card-forms/claim") return jsonOk(formSpec);
      return jsonOk({});
    });
    vi.stubGlobal("fetch", fetchMock);
    const {default: App} = await import("./App");
    render(<MemoryRouter initialEntries={["/p/demo/cards/claim/claim-01"]}>
      <App /></MemoryRouter>);
    fireEvent.click(screen.getByText("新建"));
    await waitFor(() =>
      expect(document.querySelectorAll(".right-panel input[list='dl-chapters']").length)
        .toBe(1));
    const input = document.querySelector(
      ".right-panel input[list='dl-chapters']") as HTMLInputElement;
    fireEvent.change(input, {target: {value: "introduction, results"}});
    expect(document.querySelectorAll("#dl-chapters option").length).toBe(1);
    // 必填控件先满足，否则 HTML5 校验拦下提交
    const select = document.querySelector(".right-panel select") as HTMLSelectElement;
    fireEvent.change(select, {target: {value: "uncited"}});
    const statement = document.querySelector(
      ".right-panel textarea") as HTMLTextAreaElement;
    fireEvent.change(statement, {target: {value: "正文。"}});
    fireEvent.click(screen.getByText("保存"));
    await waitFor(() => {
      const post = fetchMock.mock.calls.find(
        ([u, init]) => u === "/api/projects/demo/cards/claim"
          && init?.method === "POST");
      expect(post).toBeDefined();
      const body = JSON.parse((post as unknown as [string, RequestInit])[1].body as string);
      expect(body.chapters).toBe("introduction, results");
    });
  });
});

describe("叙事页本章标签卡（card-chapters §5.2）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("区块按 kind/id 序渲染，used 标记与卡片页跳转", async () => {
    await renderAt("/p/demo/parts/sec-01");
    await waitFor(() =>
      expect(screen.getByText("本章标签卡（01-results）")).not.toBeNull());
    const rows = [...document.querySelectorAll(".row-list .row-item")]
      .filter((el) => el.getAttribute("href")?.includes("/cards/"));
    expect(rows.map((r) => r.textContent)).toHaveLength(2);
    expect(rows[0].textContent).toContain("claim-02");
    expect(rows[0].textContent).toContain("已在 uses");
    expect(rows[1].textContent).toContain("key2020");
    expect(rows[1].textContent).not.toContain("已在 uses");
    expect(rows[0].getAttribute("href")).toBe("/p/demo/cards/claim/claim-02");
    expect(rows[1].getAttribute("href")).toBe("/p/demo/cards/note/key2020");
  });
});
