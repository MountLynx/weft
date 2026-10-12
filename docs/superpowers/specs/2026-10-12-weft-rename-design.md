# weft 改名对齐设计定案（rename：冲突审查 + 全部位点同步）

- 日期：2026-10-12
- 状态：定案（用户确认三条基线；推翻语义可见性设计 D10 的"不做 rename"）
- 关联：weft new 模板设计（N9 命名安全成分、E-NEW-* 码）、红线 5（无新增诊断码）

## 1. 目标

`weft rename <old_id> <new_id>` 一条命令完成卡片改名：冲突审查 → 卡片文件与
frontmatter id 重命名 → 全部引用位点同步改写；WebUI 卡片详情页提供同一能力的
表单入口。CLI 与 UI 共用同一个改名引擎，无第二套逻辑。

## 2. 决策表

| # | 决策 | 理由 |
|---|------|------|
| R1 | 一条命令全包（不做"手工改名后跑同步"） | 后者无法可靠建立旧→新映射，需交互猜测、误判风险高（用户确认） |
| R2 | 对象 = 六类卡片；part/节点 id 不做 | part id 只出现在 frontmatter 与 drafts 文件名，引用价值低；创建时 `--id` 已可定语义 id（用户确认，YAGNI） |
| R3 | note 改名 = bib key 改名：managed 自动重渲 bib，unmanaged 完成后打印提醒 | note id 即 bib key，cites/derived_from 全同步；references.bib 自管时仅提醒（用户确认） |
| R4 | 计划-应用两段式：`plan_rename` 纯函数（校验+扫描，零写入）→ `apply_rename` 落盘 | fail-closed：全部审查先于任何写入；计划可直接打印（`--dry-run` 零成本复用） |
| R5 | 诊断码复用 E-NEW-NAME / E-NEW-COLLISION（语义与 weft new 完全一致）；旧 id 不存在、新旧 id 相同 → 无码 ERROR 行 + 退出 1 | 红线 5 不增码表项；无码 ERROR 沿 `weft show`/`weft graph` OSError 先例 |
| R6 | 加载存在 error 级诊断即拒绝改名；不做全量 validate 闸门 | E-PARSE 卡不进内存，其文件内的引用点会漏改——安全底线；悬空引用等与改名正交（沿 weft new 的 N8 精神） |
| R7 | 落盘复用 `save_card`/`save_part`（正文原样保留、LF 归一）；顺序：写新文件 → 删旧文件 → 改写引用卡 → 改写 part → managed bib 同步 | 沿用既有写路径；新文件先落盘、旧文件后删，中断时不丢卡内容 |
| R8 | 托管 bib 同步提炼：web `_sync_managed_bib` 上移为 `bibgen.sync_managed_bib(project_root)`，web 委托调用 | CLI 与 UI 共用同一实现，消除双份逻辑 |
| R9 | WebUI：详情页「改名」表单 POST `/p/{pid}/cards/{kind}/{card_id}/rename`；成功 303 到新 id 详情页；错误回显 banner（复用现有样式） | 与卡片编辑表单的交互模式一致 |

## 3. 引擎设计（`src/weft/rename.py`）

```python
@dataclass(frozen=True)
class RenamePlan:
    kind: str                      # 卡种
    old_id: str; new_id: str
    old_rel: str; new_rel: str     # card_relpath 派生
    card_refs: dict[str, list[str]]   # 引用卡 id → 受影响字段名列表（data/supports/cites/method/derived_from）
    part_refs: dict[str, int]         # part id → uses 改写处数
    needs_bib_sync: bool              # kind == "note" 且 bib_managed

def plan_rename(project, old_id, new_id) -> RenamePlan
    # 旧 id 不存在 / new == old      → RenameError（无码）
    # new_id 非法路径成分（N9 规则） → scaffold.NewNameError（E-NEW-NAME）
    # new_id 已被任何卡占用          → scaffold.NewCollisionError（E-NEW-COLLISION）

def apply_rename(project, plan) -> RenameResult   # written: list[Path], bib_status: str | None
```

- 引用扫描与校验器引用语义一致（穷举）：`fact.data`、`fact.supports`、
  `claim.cites`、`param.method`、`param.derived_from`、`method.derived_from`、
  全部叙事节点的 `uses[].id`（role 原样保留）；同名卡多处引用按卡聚合。
  `data.refs` 是图号不是卡 id，不动；drafts/、generated/ 是派生产物，不动。
- N9 校验复用 `scaffold._ensure_component`；改名的卡自身不进引用改写列表
  （内容随文件迁移）。
- managed bib 同步（R8）：`bibgen.sync_managed_bib(project_root)` 复用现有
  `sync_bib`；unmanaged（或 bib 文件不唯一）时返回 None，调用方打印提醒。

## 4. CLI

```
weft rename <old_id> <new_id> [project_dir] [--dry-run]
```

- 输出（成功）：

```
改写计划：
  重命名  metadata/facts/fact-01.md → metadata/facts/rate-jumps-above-60c.md
  同步    metadata/facts/fact-02.md（data 1 处）
  同步    narrative/03-results/part-01.md（uses 1 处）
✓ 3 个文件已更新
```

- `--dry-run` 只打印计划与 `(dry-run，未写入)`，退出码 0，零落盘；
- 失败路径：E-NEW-NAME / E-NEW-COLLISION 打印诊断退出 1（零写入）；无码 ERROR
  打印 `ERROR <原因>` 退出 1；加载 error 诊断打印全部诊断退出 1（R6）。

## 5. WebUI

卡片详情页（`card_detail.html`）新增「改名」内联表单（新 id 输入 + 提交按钮）；
POST 到 rename 路由，内部调 `plan_rename` + `apply_rename`：
成功 → 303 到新 id 详情页；`RenameError`/`NewNameError`/`NewCollisionError` →
详情页回显错误 banner（复用 `banner error` 类），零写入保证不变。

## 6. 兼容性与风险

- 跨文件改写无事务：计划段已排除碰撞与合法性，写入顺序 R7 使中断最坏情形是
  "新卡已建、旧卡未删"（数据不丢，重跑 rename 报碰撞可人工恢复）——计划文档记录该边界；
- 黄金文件不受影响（graph.json 由 `weft graph` 再生成，rename 不触 generated/）；
- schema、诊断码表、主题令牌均不动。

## 7. 验收

1. `weft rename` 后：新文件在、旧文件无、frontmatter id 与文件名一致、
   全部引用位点（含 part uses）指向新 id，`weft validate` 通过；
2. `--dry-run` 零落盘；碰撞/非法名/未知 id/带错项目各自报对退出码；
3. note 改名在 managed 项目中同步 references.bib；unmanaged 打印提醒；
4. WebUI 详情页改名成功跳转新 id 页；冲突回显错误且零写入；
5. 全量测试绿（精确计数见实施计划）。
