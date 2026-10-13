import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// 构建产物进 Python 包静态目录（提交入库，wheel 分发 + 离线可运行，设计 D8）；
// base 必须与 FastAPI 挂载点一致（/static/app/）。
export default defineConfig({
  plugins: [react()],
  base: "/static/app/",
  build: {
    outDir: "../src/weft/web/static/app",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/static": "http://127.0.0.1:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./src/test-setup.ts",
  },
} as never);
