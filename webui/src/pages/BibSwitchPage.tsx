/** bib 模式切换确认页：预检 plan + 确认执行（E-BIB-MODE 呈现）。 */
import {useState} from "react";
import {useNavigate, useParams, useSearchParams} from "react-router-dom";
import {api, ApiError} from "../api/client";
import type {SwitchPayload} from "../api/types";
import {useApi} from "../hooks/useApi";
import {Icon} from "../components/Icon";
import {toast} from "../state/toast";

export function BibSwitchPage() {
  const {pid = ""} = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const to = params.get("to") === "unmanaged" ? "unmanaged" : "managed";
  const {data, reload} = useApi<SwitchPayload>(
    `/api/projects/${encodeURIComponent(pid)}/bib/switch?to=${to}`);
  const [busy, setBusy] = useState(false);

  async function confirm() {
    setBusy(true);
    try {
      await api.post(`/api/projects/${encodeURIComponent(pid)}/bib/switch`, {to});
      toast.success(`已切换为 ${to}`);
      navigate(`/p/${encodeURIComponent(pid)}`);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.detail : String(err));
      reload();
    } finally {
      setBusy(false);
    }
  }

  const plan = data?.plan;

  return (
    <main className="center">
      <div className="page-head">
        <h2>bib 模式切换 → {to}</h2>
      </div>
      <div className="page-body">
        <button className="ghost" onClick={() => navigate(-1)}>
          <Icon name="arrow-left" size={14} />返回
        </button>
        {data?.error && <div className="banner error">{data.error}</div>}
        {plan && (
          <>
            <div className="banner">
              <div>
                {plan.from_managed ? "managed" : "unmanaged"} →{" "}
                {plan.to_managed ? "managed" : "unmanaged"}；bib 目标：
                <span className="badge mono">{plan.bib_files.join("、") || "（无）"}</span>
              </div>
            </div>
            {plan.hand_only_entries.length > 0 && (
              <div className="banner warning">
                <div>以下 key 在 bib 中但无 approved+entry 卡覆盖，切换后下次 sync 将从 bib 消失：</div>
                {plan.hand_only_entries.map((k) => (
                  <span key={k} className="badge mono">{k}</span>
                ))}
              </div>
            )}
            {plan.notes_not_in_bib.length > 0 && (
              <div className="banner warning">
                <div>以下非 rejected note 不在 bib，切换后将报 E-NOTE-NOT-IN-BIB：</div>
                {plan.notes_not_in_bib.map((k) => (
                  <span key={k} className="badge mono">{k}</span>
                ))}
              </div>
            )}
            <div className="form-actions">
              <button className="ghost" onClick={() => navigate(-1)}>取消</button>
              <button className="primary" onClick={confirm} disabled={busy || !!data?.error}>
                <Icon name="check" size={14} />确认切换
              </button>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
