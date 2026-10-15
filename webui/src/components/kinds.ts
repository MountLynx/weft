/** 卡片种类元数据：顺序与专属图标（侧栏分组、列表行、inspector、表单头共用）。 */

export const KINDS = ["data", "fact", "claim", "note", "method", "param"] as const;

export type CardKind = (typeof KINDS)[number];

/** kind → Icon 名（feather 风格，见 Icon.tsx）。 */
export const KIND_ICONS: Record<string, string> = {
  data: "database",
  fact: "check-circle",
  claim: "message-square",
  note: "book-open",
  method: "flask",
  param: "sliders",
};

/** 未知 kind 回退到通用卡片图标。 */
export function kindIcon(kind: string | null | undefined): string {
  return (kind && KIND_ICONS[kind]) || "file-text";
}
