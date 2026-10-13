/** 文件查看：drafts/generated 白名单内的只读预览（?path=rel）。 */
import {useState} from "react";
import {useParams, useSearchParams} from "react-router-dom";
import type {FilePayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";

export function FileViewPage() {
  const {pid = ""} = useParams();
  const [params, setParams] = useSearchParams();
  const path = params.get("path") ?? "drafts/";
  const [input, setInput] = useState(path);
  const {data, error, loading} = useApi<FilePayload>(
    path && !path.endsWith("/")
      ? `/api/projects/${encodeURIComponent(pid)}/file?path=${encodeURIComponent(path)}`
      : null);

  return (
    <main className="center">
      <div className="page-head">
        <h2>文件查看</h2>
      </div>
      <div className="page-body">
        <form className="form-row" onSubmit={(e) => {
          e.preventDefault();
          setParams({path: input});
        }}>
          <label>白名单目录：drafts/ 与 generated/ 下的文件路径</label>
          <div className="row-inline">
            <input style={{flex: 1}} value={input} placeholder="drafts/sec-01.md"
                   onChange={(e) => setInput(e.target.value)} />
            <button type="submit" className="primary">
              <Icon name="file-text" size={14} />打开
            </button>
          </div>
        </form>
        {error && <div className="banner error">{error.detail}</div>}
        {loading && <div className="text-muted">加载中…</div>}
        {data && <div className="file-preview">{data.text}</div>}
      </div>
    </main>
  );
}
