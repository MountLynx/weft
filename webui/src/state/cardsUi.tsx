/** 卡片页共享 UI 态（webui-card-links 设计 §3）：/cards/links 数据 + 选中卡镜像 +
 * 筛选标签。Sidebar 筛选区与 CardsPage 过滤共用；仅 /cards/* 路由激活请求。 */
import {createContext, useCallback, useContext, useEffect, useMemo, useRef,
        useState} from "react";
import {useLocation} from "react-router-dom";
import {useApi} from "../hooks/useApi";
import type {CardLinks} from "../api/types";

export interface SelInfo {kind: string; id: string}

interface CardsUiValue {
  links: CardLinks | null;
  sel: SelInfo | null;
  reportSel: (key: string) => void;
  tags: string[];
  toggleTag: (tag: string) => void;
  clearTags: () => void;
}

const noop = () => {};
const CardsUiContext = createContext<CardsUiValue>({
  links: null, sel: null, reportSel: noop, tags: [], toggleTag: noop,
  clearTags: noop,
});

export function useCardsUi(): CardsUiValue {
  return useContext(CardsUiContext);
}

export function CardsUiProvider({pid, children}: {
  pid: string;
  children: React.ReactNode;
}) {
  const {pathname} = useLocation();
  const onCards = pathname.startsWith(`/p/${encodeURIComponent(pid)}/cards`);
  const {data} = useApi<CardLinks>(onCards
    ? `/api/projects/${encodeURIComponent(pid)}/cards/links` : null);
  // 载荷畸形（entities 缺失）按无数据降级：筛选区隐藏、过滤不生效
  const links = data !== null && data.entities !== undefined ? data : null;
  const [selKey, setSelKey] = useState("");
  const [tags, setTags] = useState<string[]>([]);

  const reportSel = useCallback((key: string) => {
    setSelKey((prev) => (prev === key ? prev : key));
  }, []);
  const toggleTag = useCallback((tag: string) => {
    setTags((prev) => prev.includes(tag)
      ? prev.filter((t) => t !== tag) : [...prev, tag]);
  }, []);
  const clearTags = useCallback(() => setTags([]), []);

  // 换选中卡即清空标签（设计 §4.4 规则 1）；links 换代（项目切换/重载）同样清空
  const prevSel = useRef(selKey);
  useEffect(() => {
    if (prevSel.current !== selKey) {
      prevSel.current = selKey;
      setTags([]);
    }
  }, [selKey]);
  const prevLinks = useRef(links);
  useEffect(() => {
    if (prevLinks.current !== links) {
      prevLinks.current = links;
      setTags([]);
    }
  }, [links]);

  const sel = useMemo<SelInfo | null>(() => {
    if (!selKey) return null;
    const slash = selKey.indexOf("/");
    return {kind: selKey.slice(0, slash), id: selKey.slice(slash + 1)};
  }, [selKey]);

  const value = useMemo<CardsUiValue>(
    () => ({links, sel, reportSel, tags, toggleTag, clearTags}),
    [links, sel, reportSel, tags, toggleTag, clearTags]);

  return <CardsUiContext.Provider value={value}>{children}</CardsUiContext.Provider>;
}
