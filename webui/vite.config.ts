import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig } from "vite";

// 构建产物进 Python 包静态目录（提交入库，wheel 分发 + 离线可运行，设计 D8）；
// base 必须与 FastAPI 挂载点一致（/static/app/）。
// dev 代理目标可用 WEFT_API 覆盖（默认 8000——weft serve 的默认端口）。
const backend = process.env.WEFT_API ?? "http://127.0.0.1:8000";

// dev 下 Vite 会给 index.html 的 /static/ 引用加 base 前缀（/static/app/static/...），
// proxy 接不住；此中间件从 Python 包的 static 目录直接供文件，保持 head 同步加载（防闪架构）。
const PKG_STATIC = resolve(__dirname, "../src/weft/web/static");
function weftStaticDev() {
  return {
    name: "weft-static-dev",
    apply: "serve" as const,
    configureServer(server: {
      middlewares: {
        use: (fn: (req: {url?: string}, res: {
          statusCode: number;
          setHeader: (k: string, v: string) => void;
          end: (data?: unknown) => void;
        }, next: () => void) => void) => void;
      };
    }) {
      server.middlewares.use((req, res, next) => {
        const match = req.url?.match(/^\/static\/app\/static\/([^?]+)$/);
        if (!match) return next();
        const rel = decodeURIComponent(match[1]);
        const ok = rel === "webui.css" || rel === "cytoscape.min.js"
          || (rel.startsWith("themes/") && rel.endsWith(".css"));
        if (!ok) {
          res.statusCode = 404;
          return res.end();
        }
        try {
          const data = readFileSync(resolve(PKG_STATIC, rel));
          res.setHeader("Content-Type",
            rel.endsWith(".css") ? "text/css; charset=utf-8"
              : "application/javascript");
          res.end(data);
        } catch {
          res.statusCode = 404;
          res.end();
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), weftStaticDev()],
  base: "/static/app/",
  build: {
    outDir: "../src/weft/web/static/app",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    // 只代理后端拥有的资源；/static/app 是 Vite 自己的 base（dev 模式下由 Vite 托管），
    // 不能转发给后端，否则 base 重定向会打到 FastAPI 上 404
    proxy: {
      "/api": backend,
      "/static/webui.css": backend,
      "/static/themes": backend,
      "/static/cytoscape.min.js": backend,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
} as never);
