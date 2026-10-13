/** 前端冒烟（不进 pytest 计数）：client 归一 / theme / toast / App 两态渲染。 */
import {describe, expect, it, vi, beforeEach, afterEach} from "vitest";
import {render, screen, waitFor, act} from "@testing-library/react";
import {MemoryRouter} from "react-router-dom";
import {ApiError, api} from "./api/client";
import {applyTheme, cycleTheme, currentTheme} from "./state/theme";
import {toast, ToastHost} from "./state/toast";

function jsonOk(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {"Content-Type": "application/json"},
  });
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });
  afterEach(() => vi.unstubAllGlobals());

  it("归一错误：detail 字符串 + errors 字典", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(
      JSON.stringify({detail: "校验失败", errors: {id: "id 非法"}}),
      {status: 422, headers: {"Content-Type": "application/json"}}));
    const err = await api.post("/api/x", {}).catch((e: ApiError) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(422);
    expect((err as ApiError).detail).toBe("校验失败");
    expect((err as ApiError).errors?.id).toBe("id 非法");
  });

  it("POST 序列化 JSON 体", async () => {
    vi.mocked(fetch).mockResolvedValue(jsonOk({ok: true}));
    await api.post("/api/x", {name: "a"});
    const init = vi.mocked(fetch).mock.calls[0][1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"name":"a"}');
  });
});

describe("theme", () => {
  it("applyTheme 写 data-theme 与 localStorage；cycle 循环", () => {
    applyTheme("");
    expect(currentTheme()).toBe("");
    cycleTheme();
    expect(currentTheme()).toBe("academic");
    cycleTheme();
    expect(currentTheme()).toBe("");
    expect(localStorage.getItem("weft-theme")).toBe("");
  });
});

describe("toast", () => {
  it("toast.error 渲染右下角堆栈", () => {
    render(<ToastHost />);
    act(() => {
      toast.error("出错了");
    });
    expect(screen.getByText("出错了")).toBeInTheDocument();
  });
});

describe("App 两态", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("项目网格渲染条目与新建 tile", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/api/projects") {
        return jsonOk({
          entries: [{pid: "demo", path: "C:/p/demo", available: true, missing: false,
                     n_cards: 4, n_errors: 0, n_warnings: 0}],
          reg_error: null, kind_labels: {}, registry_mode: false,
          projects_root: "C:/p", registry_path: "",
        });
      }
      return jsonOk({});
    }));
    const {default: App} = await import("./App");
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("demo")).toBeInTheDocument());
    expect(screen.getByText("新建项目")).toBeInTheDocument();
  });

  it("未知路径渲染 404 态", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonOk({})));
    const {default: App} = await import("./App");
    render(<MemoryRouter initialEntries={["/no/such/page"]}><App /></MemoryRouter>);
    expect(screen.getByText("页面不存在")).toBeInTheDocument();
  });
});
