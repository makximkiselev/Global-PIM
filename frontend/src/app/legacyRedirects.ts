export function legacyCompetitorWorkspaceHref(search = "") {
  const incoming = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const categoryId = String(incoming.get("category") || "").trim();
  const productId = String(incoming.get("product") || "").trim();
  if (categoryId || productId) {
    const params = new URLSearchParams();
    params.set("tab", "sources");
    if (categoryId) params.set("category", categoryId);
    if (productId) params.set("product", productId);
    return `/sources?${params.toString()}`;
  }
  const params = new URLSearchParams(incoming);
  params.set("tab", "competitors");
  return `/connectors/status?${params.toString()}`;
}
