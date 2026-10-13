import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 构建产物进 Python 包静态目录（提交入库，wheel 分发 + 离线可运行，设计 D8）；
// base 必须与 FastAPI 挂载点一致（/static/app/）。
// dev 代理目标可用 WEFT_API 覆盖（默认 8000——weft serve 的默认端口）。
const backend = process.env.WEFT_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
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
