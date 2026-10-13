/** Toast 单例：模块级 push + 右下角堆栈（itemmanage 范式，3.5s 自消）。 */
import {useEffect, useState} from "react";

export interface ToastItem {
  id: number;
  kind: "success" | "error" | "info";
  message: string;
}

type Listener = (item: ToastItem) => void;

const listeners = new Set<Listener>();
let nextId = 1;

function push(kind: ToastItem["kind"], message: string): void {
  const item: ToastItem = {id: nextId++, kind, message};
  listeners.forEach((fn) => fn(item));
}

export const toast = {
  success: (message: string) => push("success", message),
  error: (message: string) => push("error", message),
  info: (message: string) => push("info", message),
};

export function ToastHost() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const fn: Listener = (item) => {
      setItems((prev) => [...prev, item]);
      setTimeout(() => {
        setItems((prev) => prev.filter((t) => t.id !== item.id));
      }, 3500);
    };
    listeners.add(fn);
    return () => {
      listeners.delete(fn);
    };
  }, []);

  if (items.length === 0) return null;
  return (
    <div className="toast-stack">
      {items.map((t) => (
        <div key={t.id} className={`toast toast-${t.kind}`}>{t.message}</div>
      ))}
    </div>
  );
}
