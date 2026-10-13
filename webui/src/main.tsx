import React from "react";
import ReactDOM from "react-dom/client";
import {BrowserRouter} from "react-router-dom";
import App from "./App";

// dev 下应用挂在 Vite base（/static/app/）前缀；生产 shell 由后端在 / 提供，无前缀
const basename = import.meta.env.DEV ? import.meta.env.BASE_URL : "/";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter basename={basename}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
