import React from "react";
import ReactDOM from "react-dom/client";
import {BrowserRouter} from "react-router-dom";
import {mountPrefix} from "./api/mount";
import App from "./App";

// dev 下应用挂在 Vite base（/static/app/）前缀；生产 shell 由后端在 / 提供，无前缀。
// 反代子路径部署（nginx /weft/ → 8001）：代理向 shell 注入 <base href="/weft/">，
// basename 从 document.baseURI 推导（api/mount.ts 同源）；直连时无 <base>，为 "/"。
const basename = import.meta.env.DEV ? import.meta.env.BASE_URL : (mountPrefix() || "/");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
