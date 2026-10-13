/** 审阅状态徽章：draft/approved/rejected 三态。 */

const MAP: Record<string, {label: string; cls: string}> = {
  draft: {label: "draft", cls: "warning"},
  approved: {label: "approved", cls: "success"},
  rejected: {label: "rejected", cls: "danger"},
};

export function StatusBadge({status}: {status: string}) {
  const item = MAP[status] ?? {label: status, cls: ""};
  return <span className={`badge ${item.cls}`}>{item.label}</span>;
}
