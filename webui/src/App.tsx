/** App：两态布局（项目网格 ↔ 工作台）+ 路由表（webui-react 设计 §4/§6）。 */
import {Route, Routes} from "react-router-dom";
import {Sidebar} from "./components/Sidebar";
import {StatusBar} from "./components/StatusBar";
import {ToastHost} from "./state/toast";
import {Topbar} from "./components/Topbar";
import {useApi} from "./hooks/useApi";
import type {Dashboard} from "./api/types";
import {useParams} from "react-router-dom";
import {ProjectsGrid} from "./pages/ProjectsGrid";
import {Overview} from "./pages/Overview";
import {CardsPage} from "./pages/CardsPage";
import {CardFormPage} from "./pages/CardFormPage";
import {PartsPage} from "./pages/PartsPage";
import {NodeFormPage} from "./pages/NodeFormPage";
import {FiguresPage} from "./pages/FiguresPage";
import {GraphPage} from "./pages/GraphPage";
import {InspirePage} from "./pages/InspirePage";
import {ProposalComparePage} from "./pages/ProposalComparePage";
import {DiagnosticsPage} from "./pages/DiagnosticsPage";
import {BibSwitchPage} from "./pages/BibSwitchPage";
import {FileViewPage} from "./pages/FileViewPage";
import {RunConsolePage} from "./pages/RunConsolePage";

function Workspace({children}: {children: React.ReactNode}) {
  const {pid = ""} = useParams();
  const {data: dash} = useApi<Dashboard>(
    `/api/projects/${encodeURIComponent(pid)}`);
  return (
    <div className="app">
      <Topbar />
      <div className="workspace">
        <Sidebar dash={dash} />
        {children}
      </div>
      <StatusBar dash={dash} />
      <ToastHost />
    </div>
  );
}

/** 包一层以拿到 pid 上下文（Routes 内组件才可用 useParams）。 */
function WorkspaceRoute({element}: {element: React.ReactNode}) {
  return <Workspace>{element}</Workspace>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<><ProjectsGrid /><ToastHost /></>} />
      <Route path="/p/:pid" element={<WorkspaceRoute element={<Overview />} />} />
      <Route path="/p/:pid/parts" element={<WorkspaceRoute element={<PartsPage />} />} />
      <Route path="/p/:pid/parts/:partId" element={<WorkspaceRoute element={<PartsPage />} />} />
      <Route path="/p/:pid/parts/:partId/nodes/:nodeId"
             element={<WorkspaceRoute element={<NodeFormPage />} />} />
      <Route path="/p/:pid/cards" element={<WorkspaceRoute element={<CardsPage />} />} />
      <Route path="/p/:pid/cards/:kind" element={<WorkspaceRoute element={<CardsPage />} />} />
      <Route path="/p/:pid/cards/:kind/:cardId" element={<WorkspaceRoute element={<CardsPage />} />} />
      <Route path="/p/:pid/cards/:kind/new" element={<WorkspaceRoute element={<CardFormPage />} />} />
      <Route path="/p/:pid/cards/:kind/:cardId/edit"
             element={<WorkspaceRoute element={<CardFormPage />} />} />
      <Route path="/p/:pid/figures" element={<WorkspaceRoute element={<FiguresPage />} />} />
      <Route path="/p/:pid/graph" element={<WorkspaceRoute element={<GraphPage />} />} />
      <Route path="/p/:pid/inspire" element={<WorkspaceRoute element={<InspirePage />} />} />
      <Route path="/p/:pid/inspire/proposals/:cardId"
             element={<WorkspaceRoute element={<ProposalComparePage />} />} />
      <Route path="/p/:pid/diagnostics" element={<WorkspaceRoute element={<DiagnosticsPage />} />} />
      <Route path="/p/:pid/bib-switch" element={<WorkspaceRoute element={<BibSwitchPage />} />} />
      <Route path="/p/:pid/files" element={<WorkspaceRoute element={<FileViewPage />} />} />
      <Route path="/p/:pid/runs/:runId" element={<WorkspaceRoute element={<RunConsolePage />} />} />
      <Route path="*" element={
        <div className="app">
          <Topbar />
          <div className="grid-page">
            <div className="empty-state">
              <span className="big-icon">404</span>
              <div className="hint">页面不存在</div>
            </div>
          </div>
        </div>
      } />
    </Routes>
  );
}
