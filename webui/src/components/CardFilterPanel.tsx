/** 侧栏「筛选」区（webui-card-links 设计 §4.1）：选中卡的邻居标签，多选并集过滤。
 * 非卡片路由 / 无 links / 无选中卡 / 无邻居时整区隐藏。 */
import {useLocation, useParams} from "react-router-dom";
import {useCardsUi} from "../state/cardsUi";
import {linkedCount, neighborGroups} from "../state/cardLinks";
import {Icon} from "./Icon";
import {KIND_ICONS} from "./kinds";

export function CardFilterPanel() {
  const {pid = "", kind = ""} = useParams();
  const {pathname} = useLocation();
  const base = `/p/${encodeURIComponent(pid)}`;
  const {links, sel, tags, toggleTag, clearTags} = useCardsUi();
  if (!pathname.startsWith(`${base}/cards`) || links === null || sel === null) {
    return null;
  }
  const groups = neighborGroups(links, sel.id);
  if (groups.length === 0) return null;
  return (
    <div className="filter-panel">
      <div className="filter-head">
        <span className="section-label">筛选</span>
        {tags.length > 0 && (
          <button className="filter-clear" onClick={clearTags}>清除</button>
        )}
      </div>
      {groups.map((g) => (
        <div key={g.kind} className="filter-group">
          <div className="filter-kind">
            <Icon name={KIND_ICONS[g.kind] ?? "file-text"} size={12} />
            {g.kind}
          </div>
          <div className="filter-tags">
            {g.ids.map((id) => {
              const ent = links.entities[id];
              const tag = `${g.kind}/${id}`;
              return (
                <button key={id}
                        className={`tag-pill${tags.includes(tag) ? " active" : ""}`}
                        title={ent.summary || id}
                        onClick={() => toggleTag(tag)}>
                  <span className="truncate">{id}</span>
                  <span className="tag-count">
                    {linkedCount(links, kind, g.kind, id)}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
