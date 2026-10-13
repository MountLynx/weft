/** 空状态（itemmanage 范式）：居中大图标 + 文案 + 主操作。 */
import {Icon} from "./Icon";

export function EmptyState({icon, hint, action}: {
  icon: string;
  hint: string;
  action?: {label: string; onClick: () => void};
}) {
  return (
    <div className="empty-state">
      <span className="big-icon"><Icon name={icon} size={56} /></span>
      <div className="hint">{hint}</div>
      {action && (
        <button className="primary" onClick={action.onClick}>
          <Icon name="plus" size={14} />{action.label}
        </button>
      )}
    </div>
  );
}
