/** param 卡 inspector 回归：fields.values 是对象字典，须摊平渲染而非直接作为
 * React 子元素（对象子元素触发 React error #31，2026-10-31 mbgs-demo 实测）。 */
import {describe, expect, it, vi, afterEach} from "vitest";
import {render, waitFor} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), {status: 200,
    headers: {"Content-Type": "application/json"}});
}

const counts = {data: 0, fact: 0, claim: 0, note: 0, method: 1, param: 1};
const dash = {n_parts: 0, n_cards: 2, n_errors: 0, n_warnings: 0,
              kind_counts: counts, review_queue: []};
const rb = {facts: [], claims: [], methods: [], params: [], nodes: []};

const paramDetail = {
  kind: "param", label: "param 卡", id: "param-reactor-operation",
  status: "approved", comment: "",
  rel: "metadata/methods/params/param-reactor-operation.md",
  fields: {
    chapters: [],
    method: "photo-sbr-operation",
    values: {"反应器容积": "5 L（工作容积 3 L）", pH: "7.5 ± 0.1"},
    derived_from: [],
  },
  fixable: false, bib_managed: true};

async function renderParamCard() {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const handlers: Record<string, () => unknown> = {
      "/api/projects/demo": () => dash,
      "/api/projects/demo/cards/links": () => ({entities: {}}),
      "/api/projects/demo/cards/param": () => ({
        kind: "param", label: "param 卡", counts,
        rows: [{id: "param-reactor-operation", status: "approved",
                key: "photo-sbr-operation", chapters: [],
                rel: paramDetail.rel}]}),
      "/api/projects/demo/cards/param/param-reactor-operation": () => paramDetail,
    };
    const h = handlers[url] as (() => unknown) | undefined;
    return jsonOk(h ? h() : {});
  }));
  const {default: App} = await import("./App");
  render(<MemoryRouter initialEntries={["/p/demo/cards/param/param-reactor-operation"]}>
    <App />
  </MemoryRouter>);
  await waitFor(() =>
    expect(document.querySelector(".right-panel")).not.toBeNull());
}

describe("param 卡 inspector（对象字段渲染）", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("values 字典摊平为 `values.键` 行，不触发 React error #31", async () => {
    await renderParamCard();
    // 渲染完成即未崩溃；两张字典行齐备且值为字符串
    await waitFor(() => {
      const keys = [...document.querySelectorAll(".field-table .field > .k")]
        .map((el) => el.textContent);
      expect(keys).toContain("values.反应器容积");
      expect(keys).toContain("values.pH");
    });
    const rows = [...document.querySelectorAll(".field-table .field")]
      .map((el) => el.textContent);
    expect(rows.some((r) => r?.includes("反应器容积") && r.includes("5 L（工作容积 3 L）"))).toBe(true);
    expect(rows.some((r) => r?.includes("pH") && r.includes("7.5 ± 0.1"))).toBe(true);
  });

  it("空字典回退「—」，链接字段（method）仍渲染 chip", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const handlers: Record<string, () => unknown> = {
        "/api/projects/demo": () => dash,
        "/api/projects/demo/cards/links": () => ({entities: {}}),
        "/api/projects/demo/cards/param": () => ({
          kind: "param", label: "param 卡", counts,
          rows: [{id: "param-reactor-operation", status: "approved",
                  key: "photo-sbr-operation", chapters: [],
                  rel: paramDetail.rel}]}),
        "/api/projects/demo/cards/param/param-reactor-operation": () => ({
          ...paramDetail,
          fields: {...paramDetail.fields, values: {}}},
        ),
      };
      const h = handlers[url] as (() => unknown) | undefined;
      return jsonOk(h ? h() : {});
    }));
    const {default: App} = await import("./App");
    render(<MemoryRouter initialEntries={["/p/demo/cards/param/param-reactor-operation"]}>
      <App />
    </MemoryRouter>);
    await waitFor(() =>
      expect(document.querySelector(".right-panel")).not.toBeNull());
    await waitFor(() => {
      const rows = [...document.querySelectorAll(".field-table .field")]
        .map((el) => el.textContent);
      expect(rows.some((r) => r?.startsWith("values") && r.endsWith("—"))).toBe(true);
    });
    // method 是 param 的链接字段 → chip（此处无实体数据 → 悬空样式）
    const chip = document.querySelector(".field-table .chip");
    expect(chip?.textContent).toBe("photo-sbr-operation");
  });
});
