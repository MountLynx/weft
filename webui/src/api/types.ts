/** /api 端点 payload 类型（与 pydantic/service 层镜像，webui-react 设计 §3.2）。 */
import type {DiagJson} from "./client";

export interface EntryJson {
  pid: string;
  path: string;
  available: boolean;
  missing: boolean;
  n_cards: number;
  n_errors: number;
  n_warnings: number;
}

export interface ProjectsIndex {
  entries: EntryJson[];
  reg_error: string | null;
  kind_labels: Record<string, string>;
  registry_mode: boolean;
  projects_root: string | null;
  registry_path: string;
}

export interface ReviewItem {
  type: "card" | "node";
  card_kind?: string;
  part_id?: string;
  label: string;
  id: string;
  rel: string;
}

export interface Dashboard {
  available: boolean;
  pid: string;
  path?: string;
  bib_managed?: boolean;
  bib_files?: string[];
  status_counts?: Record<string, number>;
  kind_counts?: Record<string, number>;
  n_cards?: number;
  n_parts?: number;
  n_errors?: number;
  n_warnings?: number;
  diagnostics?: DiagJson[];
  review_queue?: ReviewItem[];
}

export interface DiagnosticsPayload {
  pid: string;
  available: boolean;
  n_errors: number;
  n_warnings: number;
  diagnostics: DiagJson[];
  fixable: Record<string, string>;
  kind_labels: Record<string, string>;
}

export interface SwitchPlan {
  to_managed: boolean;
  from_managed: boolean;
  bib_files: string[];
  hand_only_entries: string[];
  notes_not_in_bib: string[];
}

export interface SwitchPayload {
  to: string;
  plan: SwitchPlan | null;
  error: string | null;
}

export interface CardRow {
  id: string;
  status: string;
  key: string;
  chapters: string[];
  rel: string;
}

export interface CardsList {
  kind: string;
  label: string;
  rows: CardRow[];
  counts: Record<string, number>;
}

export interface CardDetail {
  kind: string;
  label: string;
  id: string;
  status: string;
  comment: string;
  rel: string;
  fields: Record<string, string>;
  fixable: boolean;
  bib_managed: boolean;
}

export interface FieldSpec {
  name: string;
  label: string;
  widget: string;
  choices: string | null;
  required: boolean;
}

export interface FormSpec {
  kind: string;
  label: string;
  is_new: boolean;
  id_widget: string;
  prefilled_id: string;
  id_choices: string[];
  specs: FieldSpec[];
  choices: Record<string, string[]>;
  labels: Record<string, Record<string, string>>;
  values: Record<string, unknown>;
}

export interface UseItemJson {
  id: string;
  role: string;
}

export interface PanelNode {
  id: string;
  purpose: string;
  status: string;
  comment: string;
  uses: UseItemJson[];
}

/** 本章标签卡（card-chapters 设计 §5.1）：chapters 匹配本 part 章节的卡片。 */
export interface ChapterCard {
  id: string;
  kind: string;
  status: string;
  key: string;
  used: boolean;
}

export interface PanelPayload {
  ok: boolean;
  part: {id: string; workflow: string | null};
  workflow_vocab: string[];
  chapter: string;
  chapter_norm: string;
  chapter_cards: ChapterCard[];
  nodes: PanelNode[];
  use_labels: Record<string, string>;
  draft_text: string | null;
}

export interface PartsList {
  ok: boolean;
  parts: {id: string; workflow: string | null; n_nodes: number}[];
  first: string;
}

export interface NodeFormData {
  node: {id: string; part_id: string};
  values: Record<string, unknown>;
  purpose_vocab: string[];
  role_vocab: string[];
  entity_ids: string[];
  entity_labels: Record<string, string>;
}

export interface FigureRow {
  key: string;
  caption: string;
  subfigs: Record<string, string>;
  kind: string;
  used_by: string[];
  file_missing: boolean;
  unused: boolean;
}

export interface FiguresPayload {
  rows: FigureRow[];
  load_error: string | null;
}

export interface ComparePayload {
  card_id: string;
  warn: string | null;
  rows: {key: string; old: string; new: string; changed: boolean}[] | null;
  diff_rows: {cls: string; text: string}[] | null;
  raw_new: string | null;
  old_rel: string | null;
  applicable: boolean;
}

export interface InspireList {
  proposals: {id: string}[];
}

export interface FilePayload {
  path: string;
  text: string;
}

export interface GraphPayload {
  graph: Record<string, unknown> | null;
}

export interface CardLinkEntity {
  kind: string;
  status: string;
  summary: string;
  links: Record<string, string[]>;
  referenced_by: Record<string, string[]>;
}

export interface CardLinks {
  entities: Record<string, CardLinkEntity>;
}
