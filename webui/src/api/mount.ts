/** 反代子路径挂载前缀。
 *
 * 部署在 nginx 子路径（如 /weft/）时，代理向 shell 注入 <base href="/weft/">；
 * 运行时以 "/" 开头的 URL（fetch/EventSource）不会按 <base> 的路径解析
 * （路径绝对引用只看 origin），必须显式拼接前缀。直连后端（无 <base>）返回
 * 空串，行为与上游根部署完全一致。 */

export function mountPrefix(): string {
  if (!document.querySelector("base")) return "";
  const prefix = new URL(document.baseURI).pathname.replace(/\/+$/, "");
  return prefix === "/" ? "" : prefix;
}
