/** 运行控制台页：生成/灵感管线触发后的独立 SSE 视图。 */
import {useNavigate, useParams} from "react-router-dom";
import {RunConsole} from "../components/RunConsole";
import {Icon} from "../components/Icon";

export function RunConsolePage() {
  const {pid = "", runId = ""} = useParams();
  const navigate = useNavigate();

  return (
    <main className="center">
      <div className="page-head">
        <h2>运行控制台</h2>
        <span className="badge mono">{runId}</span>
        <span className="spacer" />
        <button className="ghost" onClick={() => navigate(`/p/${encodeURIComponent(pid)}`)}>
          <Icon name="arrow-left" size={14} />返回总览
        </button>
      </div>
      <div className="page-body">
        <RunConsole pid={pid} runId={runId} />
        <div className="text-xs text-muted">
          事件经 SSE 推送；结束后返回来源页面刷新数据。
        </div>
      </div>
    </main>
  );
}
