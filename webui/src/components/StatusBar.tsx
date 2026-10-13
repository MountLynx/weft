/** StatusBar：项目路径 + E/W 计数 + 就绪态（itemmanage 范式）。 */
import type {Dashboard} from "../api/types";

export function StatusBar({dash}: {dash: Dashboard | null}) {
  return (
    <footer className="statusbar">
      <span className="truncate" style={{maxWidth: "50%"}}>
        {dash?.path ?? ""}
      </span>
      <span className="spacer" />
      {dash && (
        <>
          <span>E: {dash.n_errors ?? 0}</span>
          <span>W: {dash.n_warnings ?? 0}</span>
        </>
      )}
      <span><span className="dot" />{dash?.available === false ? "不可用" : "就绪"}</span>
    </footer>
  );
}
