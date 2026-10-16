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

function cardHandlers(): Record<string, () => unknown> {
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
    fireEvent.click(document.querySelector(".filter-head .filter-clear") as HTMLButtonElement);
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
    fireEvent.click(rows.find((r) => r.textContent?.includes("fact-03")) as HTMLElement);
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

  it("✕ 移除复原；chip 名跳转到那张卡；悬空引用 chip 警示；data 页反向邻居 pills", async () => {
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
    fireEvent.click(document.querySelector(".filter-bar .chip-x") as HTMLButtonElement);
    await waitFor(() =>
      expect(document.querySelector(".filter-bar")).toBeNull());
    // chip 名跳转：到 data-01 的 data 页
    fireEvent.click([...document.querySelectorAll(".filter-panel .tag-pill")]
      .find((p) => p.textContent?.includes("data-01")) as HTMLElement);
    await waitFor(() =>
      expect(document.querySelector(".filter-bar")).not.toBeNull());
    fireEvent.click(document.querySelector(".filter-bar .chip a") as HTMLElement);
    // 「卡片」父项与 data 子项在 /cards/* 下同为 active，首个匹配须限定子项
    await waitFor(() => expect(
      (document.querySelector("a.nav-item.sub.active") as HTMLAnchorElement)
        .getAttribute("href")).toBe("/p/demo/cards/data"));
    // D6 反向路径：data-01 的邻居（fact 组）经反向判据可达
    await waitFor(() =>
      expect(document.querySelectorAll(".filter-panel .tag-pill").length).toBe(2));
    const dataPills = [...document.querySelectorAll(".filter-panel .tag-pill")]
      .map((p) => p.textContent);
    expect(dataPills[0]).toContain("fact-01");
    expect(dataPills[1]).toContain("fact-03");
  });
});
