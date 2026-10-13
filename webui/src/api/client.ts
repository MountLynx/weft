/** API 客户端：fetch 封装，错误归一为 ApiError（设计 §6 数据流）。 */

export interface DiagJson {
  level: string;
  code: string;
  path: string;
  field: string | null;
  message: string;
  is_error: boolean;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  errors?: Record<string, string>;
  diagnostics?: DiagJson[];
  values?: Record<string, unknown>;

  constructor(status: number, payload: Record<string, unknown>) {
    const detail = payload.detail;
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = typeof detail === "string" ? detail : "";
    if (payload.errors) this.errors = payload.errors as Record<string, string>;
    if (payload.diagnostics) this.diagnostics = payload.diagnostics as DiagJson[];
    if (payload.values) this.values = payload.values as Record<string, unknown>;
  }
}

async function parseError(resp: Response): Promise<ApiError> {
  let payload: Record<string, unknown> = {};
  try {
    payload = await resp.json();
  } catch {
    /* 非 JSON 错误体（如 503 SPA 未构建） */
  }
  return new ApiError(resp.status, payload);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init);
  if (!resp.ok) throw await parseError(resp);
  if (resp.status === 204) return undefined as T;
  return (await resp.json()) as T;
}

function jsonInit(method: string, body?: unknown): RequestInit {
  return {
    method,
    headers: body === undefined ? undefined : {"Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body),
  };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) => request<T>(path, jsonInit("POST", body)),
  patch: <T>(path: string, body?: unknown) => request<T>(path, jsonInit("PATCH", body)),
  /** multipart 表单（PDF 上传等）：浏览器自设 boundary */
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, {method: "POST", body: form}),
};
