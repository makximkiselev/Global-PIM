export const PAGE_DEFAULT_PATHS: Record<string, string> = {
  dashboard: "/",
  catalog: "/catalog",
  products: "/products",
  product_groups: "/catalog/groups",
  catalog_import: "/catalog/exchange?tab=import",
  catalog_export: "/catalog/exchange?tab=export",
  templates: "/templates",
  dictionaries: "/dictionaries",
  sources_mapping: "/sources",
  connectors_status: "/connectors/status",
  infographics: "/images/infographics",
  stats_card_quality: "/stats/card-quality",
  stats_marketplace_quality: "/stats/marketplace-quality",
  admin_access: "/admin/access",
  admin_status: "/admin/status",
};

export function firstAllowedPath(pageCodes: string[]): string {
  if (pageCodes.includes("*")) return "/";
  for (const [code, path] of Object.entries(PAGE_DEFAULT_PATHS)) {
    if (pageCodes.includes(code)) return path;
  }
  return "/";
}
