import { useEffect, useMemo, useState, type DragEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import CategorySidebar from "../components/CategorySidebar";
import "../styles/marketplace-mapping.css";
import "../styles/product-groups.css";

type MainTab = "import" | "export";
type ImportTab = "categories" | "features";
type SourcesMarketplaceSectionProps = {
  embedded?: boolean;
  forcedMainTab?: MainTab;
  forcedImportTab?: ImportTab;
  hideMainTabs?: boolean;
  hideImportTabs?: boolean;
  selectedCategoryId?: string;
  onSelectedCategoryChange?: (categoryId: string, categoryName: string) => void;
  useCatalogTreeForFeatures?: boolean;
  renderCategoryDetailExtra?: (categoryId: string, categoryName: string) => ReactNode;
  renderFeatureDetailExtra?: (categoryId: string, categoryName: string) => ReactNode;
  featureView?: "marketplaces" | "competitors";
  onFeatureViewChange?: (view: "marketplaces" | "competitors") => void;
};

const SOURCES_MAPPING_CACHE_TTL_MS = 30_000;
const SOURCES_STATIC_CACHE_TTL_MS = 5 * 60_000;
let categoriesMappingCache: { ts: number; data: CategoriesResp | null } = { ts: 0, data: null };
let attrBootstrapCache: { ts: number; data: AttrBootstrapResp | null } = { ts: 0, data: null };
const attrDetailsCache = new Map<string, { ts: number; data: AttrDetailsResp }>();

type Provider = {
  code: string;
  title: string;
  count: number;
};
type DisplayProvider = Provider & { connected: boolean };

type CatalogCategory = {
  id: string;
  name: string;
  path: string;
  is_leaf: boolean;
};

type ProviderCategory = {
  id: string;
  name: string;
  path: string;
  is_leaf: boolean;
};
type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};

type CategoriesResp = {
  ok: boolean;
  catalog_nodes?: CatalogNode[];
  catalog_items: CatalogCategory[];
  providers: Provider[];
  provider_categories: Record<string, ProviderCategory[]>;
  mappings: Record<string, Record<string, string>>;
  binding_states?: Record<string, Record<string, {
    state: "direct" | "inherited_from_parent" | "aggregated_from_children" | "none";
    direct_id?: string | null;
    inherited_from?: string | null;
    inherited_id?: string | null;
    effective_id?: string | null;
    child_bindings?: Array<{
      provider_category_id: string;
      provider_category_name?: string;
      catalog_ids: string[];
      catalog_paths: string[];
    }>;
  }>>;
};

type AttrParam = {
  id: string;
  name: string;
  required?: boolean;
  kind?: string;
  values?: string[];
  system?: boolean;
};

type AttrRowProviderMap = {
  id: string;
  name: string;
  kind?: string;
  values?: string[];
  required?: boolean;
  export: boolean;
};

type AttrRow = {
  id: string;
  catalog_name: string;
  group?: string;
  provider_map: Record<string, AttrRowProviderMap>;
  confirmed: boolean;
};

type AttrCategoryItem = {
  id: string;
  name: string;
  path: string;
  mapping: Record<string, string>;
  rows_total: number;
  rows_confirmed: number;
  status: "new" | "warn" | "ok";
  group_size?: number;
  group_extra_count?: number;
  group_category_ids?: string[];
};

type AttrCategoriesResp = {
  ok: boolean;
  items: AttrCategoryItem[];
  count: number;
};

type AttrBootstrapResp = AttrCategoriesResp & {
  catalog_attr_options: CatalogAttrOption[];
  service_param_defs: ServiceParamDef[];
};

type AttrDetailsResp = {
  ok: boolean;
  category: { id: string; name: string; path: string };
  mapping: Record<string, string>;
  providers: Record<string, { category_id: string | null; params: AttrParam[]; count: number; cached?: boolean }>;
  rows: AttrRow[];
  suggested_rows?: AttrRow[];
  suggested_rows_count?: number;
  updated_at?: string | null;
  template_id?: string | null;
  master_template?: {
    version?: number;
    base_count?: number;
    category_count?: number;
    row_count?: number;
    confirmed_count?: number;
  } | null;
  sources?: Record<string, any>;
};

type AttrAiMatchResp = {
  ok: boolean;
  engine: string;
  applied: boolean;
  rows: AttrRow[];
  rows_count: number;
};

type AttrSaveResp = {
  ok: boolean;
  catalog_category_id: string;
  rows_count: number;
  saved_category_ids?: string[];
  template_id?: string | null;
  master_template?: {
    version?: number;
    base_count?: number;
    category_count?: number;
    row_count?: number;
    confirmed_count?: number;
  } | null;
  sources?: Record<string, any>;
};

type LinkResp = {
  ok: boolean;
  catalog_category_id: string;
  provider: string;
  provider_category_id: string | null;
  cleared_catalog_category_ids?: string[];
  preserved_template_category_ids?: string[];
  mappings?: Record<string, Record<string, string>>;
};

type ClearDescendantBindingsResp = {
  ok: boolean;
  catalog_category_id: string;
  provider: string;
  cleared_catalog_category_ids?: string[];
  preserved_template_category_ids?: string[];
  mappings?: Record<string, Record<string, string>>;
};

type CatalogAttrOption = {
  id: string;
  title: string;
  code?: string;
  type?: string;
  scope?: string;
  param_group?: string;
};

type ServiceParamDef = {
  key: string;
  title: string;
};

const PARAM_GROUPS = ["Артикулы", "Описание", "Медиа", "О товаре", "Логистика", "Гарантия", "Прочее"] as const;
type ParamGroup = (typeof PARAM_GROUPS)[number];

type AttrTemplateTab = "all" | "base" | "category";
type AttrRowFilter = "all" | "attention" | "ready" | "unmapped";

type AttrDraftCachePayload = {
  version: number;
  byCategory: Record<string, { rows: AttrRow[]; updated_at: string }>;
};

function qnorm(s: string) {
  return (s || "").trim().toLowerCase();
}

function humanizeParamKind(kind?: string) {
  const raw = String(kind || "").trim();
  if (!raw) return "Текст";
  const k = raw.toLowerCase();
  const map: Record<string, string> = {
    system: "Системное поле",
    boolean: "Да/Нет",
    bool: "Да/Нет",
    string: "Строка",
    text: "Текст",
    enum: "Выбор",
    select: "Выбор",
    option: "Выбор",
    options: "Выбор",
    dictionary: "Выбор",
    numeric: "Число",
    number: "Число",
    integer: "Число",
    int: "Число",
    float: "Число",
    decimal: "Число",
  };
  let out = map[k] || map[k.replace(/\s+/g, "_")] || raw;
  if (k.includes("мульти") || k.includes("multi")) out = `${out} (множественный)`;
  return out;
}

const PROVIDER_SLOTS: Record<string, string> = {
  yandex_market: "Я.Маркет",
  ozon: "Ozon",
};

const MAPPING_PROVIDER_CODES = Object.keys(PROVIDER_SLOTS);

const DEFAULT_SERVICE_PARAM_DEFS: ServiceParamDef[] = [
  { key: "sku_gt", title: "SKU GT" },
  { key: "barcode", title: "Штрихкод" },
  { key: "group", title: "Группа товара" },
  { key: "title", title: "Наименование товара" },
  { key: "brand", title: "Бренд" },
  { key: "line", title: "Линейка" },
  { key: "description", title: "Описание товара" },
  { key: "media_images", title: "Картинки" },
  { key: "media_videos", title: "Видео" },
  { key: "media_cover", title: "Видеообложка" },
  { key: "package_width", title: "Ширина упаковки, мм" },
  { key: "package_length", title: "Длина упаковки, мм" },
  { key: "package_height", title: "Высота упаковки, мм" },
  { key: "device_width", title: "Ширина устройства, мм" },
  { key: "device_length", title: "Длина устройства, мм" },
  { key: "device_height", title: "Высота устройства, мм" },
  { key: "package_weight", title: "Вес упаковки, г" },
  { key: "device_weight", title: "Вес устройства, г" },
  { key: "service_life", title: "Срок службы" },
  { key: "country_of_origin", title: "Страна производства" },
  { key: "warranty_period", title: "Гарантийный срок" },
];

const SERVICE_GROUP_BY_KEY: Record<string, ParamGroup> = {
  sku_gt: "Артикулы",
  barcode: "Артикулы",
  brand: "О товаре",
  line: "О товаре",
  description: "Описание",
  media_images: "Медиа",
  media_videos: "Медиа",
  media_cover: "Медиа",
  package_width: "Логистика",
  package_length: "Логистика",
  package_height: "Логистика",
  device_width: "Логистика",
  device_length: "Логистика",
  device_height: "Логистика",
  package_weight: "Логистика",
  device_weight: "Логистика",
  service_life: "Гарантия",
  country_of_origin: "Гарантия",
  warranty_period: "Гарантия",
};

const YANDEX_SYSTEM_TARGETS: Array<AttrParam & { serviceKey?: string }> = [
  { id: "sys:offer_id", name: "SKU / offerId", kind: "system", required: true, values: [], system: true, serviceKey: "sku_gt" },
  { id: "sys:name", name: "Наименование / name", kind: "system", required: true, values: [], system: true, serviceKey: "title" },
  { id: "sys:vendor", name: "Бренд / vendor", kind: "system", required: true, values: [], system: true, serviceKey: "brand" },
  { id: "sys:description", name: "Описание / description", kind: "system", required: false, values: [], system: true, serviceKey: "description" },
  { id: "sys:pictures", name: "Картинки / pictures", kind: "system", required: false, values: [], system: true, serviceKey: "media_images" },
  { id: "sys:barcode", name: "Штрихкод / barcode", kind: "system", required: false, values: [], system: true, serviceKey: "barcode" },
];

const YANDEX_SYSTEM_TARGET_BY_SERVICE_KEY: Record<string, AttrParam> = Object.fromEntries(
  YANDEX_SYSTEM_TARGETS.filter((x) => x.serviceKey).map((x) => [String(x.serviceKey), x])
);

const SERVICE_KEY_ALIASES: Record<string, string[]> = {
  media_images: ["картинки", "изображения", "фотографии товаров", "фотографии", "фото", "галерея", "gallery", "images"],
  description: ["описание товара", "описание", "аннотация", "description"],
  package_width: ["ширина упаковки", "ширина упаковки, мм", "ширина", "ширина, мм", "ширина мм"],
  package_length: [
    "длина упаковки",
    "длина упаковки, мм",
    "длина",
    "длина, мм",
    "длина мм",
    "глубина упаковки",
    "глубина упаковки, мм",
    "глубина",
    "глубина, мм",
    "глубина мм",
  ],
  package_height: ["высота упаковки", "высота упаковки, мм", "высота", "высота, мм", "высота мм"],
  package_weight: ["вес упаковки", "вес упаковки, г", "вес", "вес, г", "вес г", "вес брутто", "вес брутто, г"],
  device_width: ["ширина устройства", "ширина устройства, мм", "ширина товара", "ширина корпуса"],
  device_length: [
    "длина устройства",
    "длина устройства, мм",
    "длина товара",
    "длина корпуса",
    "глубина устройства",
    "глубина устройства, мм",
    "глубина товара",
    "глубина товара, мм",
    "глубина корпуса",
    "глубина корпуса, мм",
  ],
  device_height: ["высота устройства", "высота устройства, мм", "высота товара", "высота корпуса"],
  device_weight: [
    "вес устройства",
    "вес устройства, г",
    "вес товара",
    "вес устройства без упаковки",
    "вес нетто",
    "вес нетто, г",
  ],
  country_of_origin: ["страна производства", "страна изготовитель", "страна изготовителя", "страна происхождения", "страна сборки"],
  warranty_period: ["гарантийный срок", "гарантия", "срок гарантии", "гарантия производителя"],
  service_life: ["срок службы", "срок эксплуатации"],
};

function serviceRowId(key: string) {
  return `svc:${key}`;
}

function defaultProviderMap(): Record<string, AttrRowProviderMap> {
  return Object.fromEntries(
    MAPPING_PROVIDER_CODES.map((code) => [code, { id: "", name: "", kind: "", values: [], required: false, export: false }])
  ) as Record<string, AttrRowProviderMap>;
}

function isServiceRow(row: AttrRow, serviceDefs: ServiceParamDef[]) {
  const rid = String(row.id || "");
  if (rid.startsWith("svc:")) {
    const key = rid.slice(4);
    return serviceDefs.some((x) => x.key === key);
  }
  if (serviceKeyFromRow(row, serviceDefs)) return true;
  const nm = qnorm(row.catalog_name || "");
  return serviceDefs.some((x) => qnorm(x.title) === nm);
}

function normalizeServiceKey(keyRaw: string): string {
  const key = String(keyRaw || "").trim().toLowerCase();
  if (key === "media") return "media_images";
  return key;
}

function serviceKeyFromRow(row: AttrRow, serviceDefs: ServiceParamDef[]): string {
  const rid = String(row.id || "");
  if (rid.startsWith("svc:")) return normalizeServiceKey(rid.slice(4));
  const nm = qnorm(row.catalog_name || "");
  const found = serviceDefs.find((x) => qnorm(x.title) === nm);
  if (found?.key) return found.key;
  for (const [serviceKey, aliases] of Object.entries(SERVICE_KEY_ALIASES)) {
    if (aliases.some((alias) => qnorm(alias) === nm)) return serviceKey;
  }
  return "";
}

function enforceServiceRowsTop(rowsIn: AttrRow[], serviceDefs: ServiceParamDef[]): AttrRow[] {
  const rows = (Array.isArray(rowsIn) ? [...rowsIn] : []).map((row) => ({
    ...row,
    catalog_name: humanizeCatalogName(row.catalog_name || ""),
  }));
  const byServiceKey = new Map<string, AttrRow>();

  for (const row of rows) {
    const rid = String(row.id || "");
    let key = "";
    if (rid.startsWith("svc:")) key = normalizeServiceKey(rid.slice(4));
    if (!key) {
      const nm = qnorm(row.catalog_name || "");
      const found = serviceDefs.find((x) => qnorm(x.title) === nm)
        || (["медиа", "media"].includes(nm) ? serviceDefs.find((x) => x.key === "media_images") : undefined);
      if (!found) {
        for (const [serviceKey, aliases] of Object.entries(SERVICE_KEY_ALIASES)) {
          if (aliases.some((alias) => qnorm(alias) === nm)) {
            const aliasFound = serviceDefs.find((x) => x.key === serviceKey);
            if (aliasFound) {
              key = aliasFound.key;
              break;
            }
          }
        }
      }
      if (found) key = found.key;
    }
    if (key && !serviceDefs.some((x) => x.key === key)) key = "";
    if (!key) continue;
    if (!byServiceKey.has(key)) {
      byServiceKey.set(key, {
        ...row,
        id: serviceRowId(key),
        catalog_name: serviceDefs.find((x) => x.key === key)?.title || row.catalog_name || "",
        // Keep user-selected group editable; use defaults only when empty.
        group: normalizeParamGroup(row.group, serviceDefs.find((x) => x.key === key)?.title || row.catalog_name || ""),
        provider_map: Object.fromEntries(
          MAPPING_PROVIDER_CODES.map((code) => [code, { id: "", name: "", kind: "", values: [], export: false, ...(row.provider_map?.[code] || {}) }])
        ) as Record<string, AttrRowProviderMap>,
      });
    }
  }

  const serviceRows: AttrRow[] = serviceDefs.map((def) => {
    const existing = byServiceKey.get(def.key);
    if (existing) return existing;
    const providerMap = defaultProviderMap();
    return {
      id: serviceRowId(def.key),
      catalog_name: def.title,
      group: SERVICE_GROUP_BY_KEY[def.key] || normalizeParamGroup("", def.title),
      provider_map: providerMap,
      confirmed: false,
    };
  });

  const customRows = rows
    .filter((row) => !isServiceRow(row, serviceDefs))
    .map((row) => ({ ...row, group: normalizeParamGroup(row.group, row.catalog_name) }));

  // Deduplicate custom rows by normalized catalog name.
  const dedupedCustom: AttrRow[] = [];
  const byName = new Map<string, number>();
  for (const row of customRows) {
    const key = qnorm(row.catalog_name || "");
    if (!key) {
      dedupedCustom.push(row);
      continue;
    }
    const idx = byName.get(key);
    if (idx === undefined) {
      byName.set(key, dedupedCustom.length);
      dedupedCustom.push(row);
      continue;
    }
    const cur = dedupedCustom[idx];
    const mergedProviderMap: Record<string, AttrRowProviderMap> = { ...(cur.provider_map || {}) };
    for (const providerCode of MAPPING_PROVIDER_CODES) {
      const curValue = cur.provider_map?.[providerCode] || { id: "", name: "", kind: "", values: [], export: false };
      const rowValue = row.provider_map?.[providerCode] || { id: "", name: "", kind: "", values: [], export: false };
      mergedProviderMap[providerCode] =
        !String(curValue.id || "").trim() && String(rowValue.id || "").trim() ? rowValue : curValue;
    }
    dedupedCustom[idx] = {
      ...cur,
      confirmed: !!cur.confirmed || !!row.confirmed,
      provider_map: mergedProviderMap,
    };
  }

  const combined = [...serviceRows, ...dedupedCustom];
  const usedIds = new Set<string>();
  return combined.map((row, index) => {
    const baseId = String(row.id || "").trim() || `row_${index + 1}`;
    if (!usedIds.has(baseId)) {
      usedIds.add(baseId);
      return row;
    }
    let seq = 2;
    let nextId = `${baseId}__${seq}`;
    while (usedIds.has(nextId)) {
      seq += 1;
      nextId = `${baseId}__${seq}`;
    }
    usedIds.add(nextId);
    return { ...row, id: nextId };
  });
}

function applyYandexSystemBindings(rowsIn: AttrRow[], serviceDefs: ServiceParamDef[]): AttrRow[] {
  return (Array.isArray(rowsIn) ? rowsIn : []).map((row) => {
    const serviceKey = serviceKeyFromRow(row, serviceDefs);
    const target = YANDEX_SYSTEM_TARGET_BY_SERVICE_KEY[serviceKey];
    if (!target) return row;
    const current = row.provider_map?.yandex_market || { id: "", name: "", kind: "", values: [], required: false, export: false };
    if (String(current.id || "").trim()) return row;
    return {
      ...row,
      provider_map: {
        ...(row.provider_map || {}),
        yandex_market: {
          id: String(target.id),
          name: String(target.name),
          kind: String(target.kind || "system"),
          values: [],
          required: !!target.required,
          export: true,
        },
      },
      confirmed: row.confirmed || !!target.required,
    };
  });
}

function mergeRowsWithCatalogOptions(
  rowsIn: AttrRow[],
  options: CatalogAttrOption[],
  serviceDefs: ServiceParamDef[]
): AttrRow[] {
  const rows = Array.isArray(rowsIn) ? [...rowsIn] : [];
  const existingNames = new Set(rows.map((r) => qnorm(r.catalog_name || "")).filter(Boolean));
  const serviceNames = new Set((serviceDefs || []).map((s) => qnorm(s.title || "")).filter(Boolean));

  for (const opt of options || []) {
    const title = String(opt?.title || "").trim();
    if (!title) continue;
    const norm = qnorm(title);
    if (!norm) continue;
    if (existingNames.has(norm)) continue;
    if (serviceNames.has(norm)) continue;

    const rowIdBase = String(opt.id || opt.code || title).trim().replace(/\s+/g, "_");
    rows.push({
      id: `catattr:${rowIdBase}`,
      catalog_name: title,
      group: normalizeParamGroup(String(opt.param_group || ""), title),
      provider_map: defaultProviderMap(),
      confirmed: false,
    });
    existingNames.add(norm);
  }
  return rows;
}

function alignRowsWithCatalogGroups(rowsIn: AttrRow[], options: CatalogAttrOption[]): AttrRow[] {
  const rows = Array.isArray(rowsIn) ? [...rowsIn] : [];
  const groupByName = new Map<string, string>();
  for (const opt of options || []) {
    const n = qnorm(String(opt?.title || ""));
    const g = String(opt?.param_group || "").trim();
    if (!n || !g) continue;
    if (!groupByName.has(n)) groupByName.set(n, g);
  }
  return rows.map((r) => {
    const mapped = groupByName.get(qnorm(r.catalog_name || ""));
    if (!mapped) return r;
    const nextGroup = normalizeParamGroup(mapped, r.catalog_name || "");
    if (nextGroup === normalizeParamGroup(r.group, r.catalog_name || "")) return r;
    return { ...r, group: nextGroup };
  });
}

function classifyParamGroup(name?: string): ParamGroup {
  const s = String(name || "").toLowerCase();
  if (/(описани|аннотац)/i.test(s)) return "Описание";
  if (/(картин|изображ|фото|video|видеооблож|видео|медиа)/i.test(s)) return "Медиа";
  if (/(sku|штрихкод|barcode|партномер|код продавца|серийн)/i.test(s)) return "Артикулы";
  if (/(страна производства|страна происхождения|страна сборки|гарант|срок службы)/i.test(s)) return "Гарантия";
  if (/(вес|ширина|высота|толщина|размер|длина кабеля|упаков|количество|габарит)/i.test(s)) return "Логистика";
  return "О товаре";
}

function normalizeParamGroup(group?: string, name?: string): ParamGroup {
  const g = String(group || "").trim() as ParamGroup;
  if (PARAM_GROUPS.includes(g)) return g;
  return classifyParamGroup(name);
}

function humanizeCatalogName(nameRaw?: string): string {
  const s = String(nameRaw || "").trim();
  if (!s) return "";
  const directKnown: Record<string, string> = {
    "артикул": "Партномер",
    "артикул производителя": "Партномер",
    "изображение для миниатюры": "Картинки",
    "название группы вариантов": "Группа товара",
    "вес": "Вес упаковки, г",
    "вес, г": "Вес упаковки, г",
    "ширина": "Ширина упаковки, мм",
    "высота": "Высота упаковки, мм",
    "длина": "Длина упаковки, мм",
    "глубина": "Длина упаковки, мм",
    "вес,г": "Вес упаковки, г",
    "ширина,мм": "Ширина упаковки, мм",
    "ширина, мм": "Ширина упаковки, мм",
    "высота,мм": "Высота упаковки, мм",
    "высота, мм": "Высота упаковки, мм",
    "длина,мм": "Длина упаковки, мм",
    "длина, мм": "Длина упаковки, мм",
  };
  const sNorm = qnorm(s);
  if (directKnown[sNorm]) return directKnown[sNorm];
  if (!s.toLowerCase().startsWith("dict_")) return s;
  const key = s.slice(5).trim().toLowerCase();
  const known: Record<string, string> = {
    sku_gt: "SKU GT",
    barcode: "Штрихкод",
    штрихкод: "Штрихкод",
    партномер: "Партномер",
    артикул: "Партномер",
    артикул_производителя: "Партномер",
    изображение_для_миниатюры: "Картинки",
    название_группы_вариантов: "Группа товара",
    весг: "Вес упаковки, г",
    ширинамм: "Ширина упаковки, мм",
    высотамм: "Высота упаковки, мм",
    длинамм: "Длина упаковки, мм",
    наличие_серии: "Серия",
  };
  if (known[key]) return known[key];
  const txt = key.replace(/_/g, " ").trim();
  return txt ? txt.charAt(0).toUpperCase() + txt.slice(1) : s;
}

function canonicalLogisticsTitle(rawName?: string): string {
  const nm = qnorm(rawName || "");
  if (!nm) return "";
  if (["ширина", "ширина, мм", "ширина мм", "ширина,мм"].includes(nm)) return "Ширина упаковки, мм";
  if (["длина", "длина, мм", "длина мм", "длина,мм", "глубина", "глубина, мм", "глубина мм", "глубина,мм"].includes(nm)) return "Длина упаковки, мм";
  if (["высота", "высота, мм", "высота мм", "высота,мм"].includes(nm)) return "Высота упаковки, мм";
  if (["ширина упаковки", "ширина упаковки, мм"].includes(nm)) return "Ширина упаковки, мм";
  if (["длина упаковки", "длина упаковки, мм", "глубина упаковки", "глубина упаковки, мм"].includes(nm)) return "Длина упаковки, мм";
  if (["высота упаковки", "высота упаковки, мм"].includes(nm)) return "Высота упаковки, мм";
  if (["вес", "вес, г", "вес г", "вес,г", "вес упаковки", "вес упаковки, г", "вес брутто", "вес брутто, г"].includes(nm)) return "Вес упаковки, г";
  if (["ширина устройства", "ширина устройства, мм", "ширина товара", "ширина корпуса"].includes(nm)) return "Ширина устройства, мм";
  if (["длина устройства", "длина устройства, мм", "длина товара", "длина корпуса", "глубина устройства", "глубина устройства, мм", "глубина товара", "глубина товара, мм", "глубина корпуса", "глубина корпуса, мм"].includes(nm)) return "Длина устройства, мм";
  if (["высота устройства", "высота устройства, мм", "высота товара", "высота корпуса"].includes(nm)) return "Высота устройства, мм";
  if (["вес устройства", "вес устройства, г", "вес товара", "вес устройства без упаковки", "вес нетто", "вес нетто, г"].includes(nm)) return "Вес устройства, г";
  return "";
}

const ATTR_DRAFT_CACHE_KEY = "mm_attr_mapping_draft_v4";

function loadAttrDraftCache(): AttrDraftCachePayload {
  try {
    const raw = window.localStorage.getItem(ATTR_DRAFT_CACHE_KEY);
    if (!raw) return { version: 1, byCategory: {} };
    const parsed = JSON.parse(raw);
    const byCategory = parsed?.byCategory;
    if (!parsed || typeof parsed !== "object" || typeof byCategory !== "object" || Array.isArray(byCategory)) {
      return { version: 1, byCategory: {} };
    }
    return {
      version: 1,
      byCategory: byCategory as Record<string, { rows: AttrRow[]; updated_at: string }>,
    };
  } catch {
    return { version: 1, byCategory: {} };
  }
}

function saveAttrDraftCache(payload: AttrDraftCachePayload) {
  try {
    window.localStorage.setItem(ATTR_DRAFT_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // ignore cache write issues
  }
}

function hasMeaningfulSavedRows(rowsIn: AttrRow[] | undefined | null): boolean {
  const rows = Array.isArray(rowsIn) ? rowsIn : [];
  for (const row of rows) {
    if (!row || typeof row !== "object") continue;
    if (row.confirmed) return true;
    if (MAPPING_PROVIDER_CODES.some((providerCode) => String(row.provider_map?.[providerCode]?.id || "").trim() || String(row.provider_map?.[providerCode]?.name || "").trim())) return true;
  }
  return false;
}

function buildDraftRowsFromYandexParams(
  params: AttrParam[] | undefined,
  catalogOptions: CatalogAttrOption[],
  serviceDefs: ServiceParamDef[]
): AttrRow[] {
  const items = Array.isArray(params) ? params : [];
  if (!items.length) return [];
  const optionByName = new Map<string, CatalogAttrOption>();
  for (const opt of catalogOptions || []) {
    const key = qnorm(opt?.title || "");
    if (key && !optionByName.has(key)) optionByName.set(key, opt);
  }
  const serviceTitles = new Set((serviceDefs || []).map((item) => qnorm(item.title)));
  const rows: AttrRow[] = [];
  const seen = new Set<string>();

  for (const item of items) {
    const rawName = String(item?.name || "").trim();
    if (!rawName) continue;
    const normName = qnorm(rawName);
    if (!normName || serviceTitles.has(normName) || seen.has(normName)) continue;
    seen.add(normName);
    const matchedOption = optionByName.get(normName);
    const title = canonicalLogisticsTitle(matchedOption?.title || rawName) || humanizeCatalogName(matchedOption?.title || rawName);
    rows.push({
      id: `ym:${String(item.id || rawName).replace(/\s+/g, "_")}`,
      catalog_name: title,
      group: normalizeParamGroup(String(matchedOption?.param_group || ""), title),
      provider_map: {
        yandex_market: {
          id: String(item.id || ""),
          name: rawName,
          kind: String(item.kind || ""),
          values: Array.isArray(item.values) ? item.values : [],
          required: !!item.required,
          export: true,
        },
        ozon: {
          id: "",
          name: "",
          kind: "",
          values: [],
          required: false,
          export: false,
        },
      },
      confirmed: false,
    });
  }
  return rows;
}

export default function SourcesMarketplaceSection(props: SourcesMarketplaceSectionProps = {}) {
  const {
    embedded = false,
    forcedMainTab,
    forcedImportTab,
    hideMainTabs = false,
    hideImportTabs = false,
    selectedCategoryId: controlledSelectedCategoryId = "",
    onSelectedCategoryChange,
    useCatalogTreeForFeatures = false,
    renderCategoryDetailExtra,
    renderFeatureDetailExtra,
    featureView = "marketplaces",
    onFeatureViewChange,
  } = props;
  const [mainTab, setMainTab] = useState<MainTab>(forcedMainTab || "import");
  const [importTab, setImportTab] = useState<ImportTab>(forcedImportTab || "categories");

  const [loading, setLoading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [syncMsg, setSyncMsg] = useState<string>("");

  const [catalogItems, setCatalogItems] = useState<CatalogCategory[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [providerCategories, setProviderCategories] = useState<Record<string, ProviderCategory[]>>({});
  const [mappings, setMappings] = useState<Record<string, Record<string, string>>>({});

  const [attrCategories, setAttrCategories] = useState<AttrCategoryItem[]>([]);
  const [attrCategoriesLoading, setAttrCategoriesLoading] = useState(false);
  const [attrSelectedCategoryId, setAttrSelectedCategoryId] = useState("");
  const [attrDetailsLoading, setAttrDetailsLoading] = useState(false);
  const [attrDetails, setAttrDetails] = useState<AttrDetailsResp | null>(null);
  const [attrDetailsError, setAttrDetailsError] = useState("");
  const [attrRows, setAttrRows] = useState<AttrRow[]>([]);
  const [attrSaving, setAttrSaving] = useState(false);
  const [attrAiMatching, setAttrAiMatching] = useState(false);
  const [attrEditMode, setAttrEditMode] = useState(true);
  const [attrHasServerSaved, setAttrHasServerSaved] = useState(false);
  const [attrDraftExists, setAttrDraftExists] = useState(false);
  const [catalogAttrOptions, setCatalogAttrOptions] = useState<CatalogAttrOption[]>([]);
  const [serviceParamDefs, setServiceParamDefs] = useState<ServiceParamDef[]>(DEFAULT_SERVICE_PARAM_DEFS);
  const [attrTemplateTab, setAttrTemplateTab] = useState<AttrTemplateTab>("all");
  const [attrRowFilter, setAttrRowFilter] = useState<AttrRowFilter>("attention");
  const [attrRowQuery, setAttrRowQuery] = useState("");
  const [dragParamKey, setDragParamKey] = useState("");
  const [dragProvider, setDragProvider] = useState("");
  const [dropCellKey, setDropCellKey] = useState("");
  const [pendingScrollRowId, setPendingScrollRowId] = useState("");
  const [pendingScrollFocus, setPendingScrollFocus] = useState(false);

  const [catalogQuery, setCatalogQuery] = useState("");
  const [selectedCatalogIdState, setSelectedCatalogIdState] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [modalProvider, setModalProvider] = useState("");
  const [modalCatalogCategoryId, setModalCatalogCategoryId] = useState("");
  const [modalSelectedProviderCategoryId, setModalSelectedProviderCategoryId] = useState("");
  const [modalQuery, setModalQuery] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedToast, setSavedToast] = useState(false);
  const [savedTemplateId, setSavedTemplateId] = useState("");
  const [savedToastText, setSavedToastText] = useState("Сохранено");
  const [catalogNodes, setCatalogNodes] = useState<CatalogNode[]>([]);
  const [bindingStates, setBindingStates] = useState<CategoriesResp["binding_states"]>({});
  const [treeExpanded, setTreeExpanded] = useState<Record<string, boolean>>({});
  const [attrCacheHydratedFor, setAttrCacheHydratedFor] = useState("");
  const [attrDraftAutoBuilt, setAttrDraftAutoBuilt] = useState(false);
  const [clearModalOpen, setClearModalOpen] = useState(false);
  const [clearModalProvider, setClearModalProvider] = useState("");
  const [clearModalCategoryId, setClearModalCategoryId] = useState("");
  const [clearModalPreserveTemplates, setClearModalPreserveTemplates] = useState(true);
  const selectedCatalogId = controlledSelectedCategoryId || selectedCatalogIdState;
  const activeAttrCategoryId = useCatalogTreeForFeatures ? (selectedCatalogId || attrSelectedCategoryId) : attrSelectedCategoryId;

  function applySelectedCatalogId(nextId: string) {
    if (!controlledSelectedCategoryId) {
      setSelectedCatalogIdState(nextId);
    }
    const node = catalogNodes.find((item) => item.id === nextId);
    onSelectedCategoryChange?.(nextId, node?.name || "");
  }

  useEffect(() => {
    if (forcedMainTab && mainTab !== forcedMainTab) setMainTab(forcedMainTab);
  }, [forcedMainTab, mainTab]);

  useEffect(() => {
    if (forcedImportTab && importTab !== forcedImportTab) setImportTab(forcedImportTab);
  }, [forcedImportTab, importTab]);

  async function loadCategoriesMapping(): Promise<CategoriesResp | null> {
    const now = Date.now();
    if (categoriesMappingCache.data && now - categoriesMappingCache.ts < SOURCES_MAPPING_CACHE_TTL_MS) {
      const data = categoriesMappingCache.data;
      setCatalogNodes(data.catalog_nodes || []);
      setCatalogItems(data.catalog_items || []);
      setProviders(data.providers || []);
      setProviderCategories(data.provider_categories || {});
      setMappings(data.mappings || {});
      setBindingStates(data.binding_states || {});
      return data;
    }
    setLoading(true);
    setErr(null);
    try {
      const data = await api<CategoriesResp>("/marketplaces/mapping/import/categories");
      categoriesMappingCache = { ts: Date.now(), data };
      setCatalogNodes(data.catalog_nodes || []);
      setCatalogItems(data.catalog_items || []);
      setProviders(data.providers || []);
      setProviderCategories(data.provider_categories || {});
      setMappings(data.mappings || {});
      setBindingStates(data.binding_states || {});
      return data;
    } catch (e) {
      setErr((e as Error).message || "Ошибка загрузки");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function loadInitialReadModel() {
    const data = await loadCategoriesMapping();
    if (data) {
      setSyncMsg("");
    }
  }

  async function loadAttrBootstrap() {
    const now = Date.now();
    setAttrCategoriesLoading(true);
    try {
      const r =
        attrBootstrapCache.data && now - attrBootstrapCache.ts < SOURCES_STATIC_CACHE_TTL_MS
          ? attrBootstrapCache.data
          : await api<AttrBootstrapResp>("/marketplaces/mapping/import/attributes/bootstrap");
      attrBootstrapCache = { ts: Date.now(), data: r };
      const items = r.items || [];
      setAttrCategories(items);
      setCatalogAttrOptions(r.catalog_attr_options || []);
      setServiceParamDefs((r.service_param_defs || []).length ? (r.service_param_defs || []) : DEFAULT_SERVICE_PARAM_DEFS);
      if (items.length === 0) {
        setAttrSelectedCategoryId("");
      } else if (useCatalogTreeForFeatures && selectedCatalogId) {
        if (attrSelectedCategoryId !== selectedCatalogId) {
          setAttrSelectedCategoryId(selectedCatalogId);
        }
      } else if (!attrSelectedCategoryId || !items.some((x) => x.id === attrSelectedCategoryId)) {
        setAttrSelectedCategoryId(items[0].id);
        if (useCatalogTreeForFeatures) {
          applySelectedCatalogId(items[0].id);
        }
      }
    } finally {
      setAttrCategoriesLoading(false);
    }
  }

  async function loadAttrDetails(categoryId: string) {
    if (!categoryId) {
      setAttrDetails(null);
      setAttrRows([]);
      setAttrDetailsError("");
      return;
    }
    setAttrDetailsLoading(true);
    setAttrDetailsError("");
    try {
      const defs = serviceParamDefs.length ? serviceParamDefs : DEFAULT_SERVICE_PARAM_DEFS;
      const cachedDetails = attrDetailsCache.get(categoryId);
      let data =
        cachedDetails && Date.now() - cachedDetails.ts < SOURCES_MAPPING_CACHE_TTL_MS
          ? cachedDetails.data
          : await api<AttrDetailsResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(categoryId)}`);
      attrDetailsCache.set(categoryId, { ts: Date.now(), data });
      setAttrDetails(data);
      setSavedTemplateId(String(data.template_id || ""));
      let rowsSource: AttrRow[] = (data.rows || []) as AttrRow[];
      const cache = loadAttrDraftCache();
      const cached = cache.byCategory?.[categoryId];
      const hasServerSaved = !!data.updated_at && hasMeaningfulSavedRows((data.rows || []) as AttrRow[]);
      setAttrHasServerSaved(hasServerSaved);
      setAttrEditMode(true);
      setAttrDraftExists(!!(cached && Array.isArray(cached.rows) && cached.rows.length > 0));
      if (!hasServerSaved && cached && Array.isArray(cached.rows) && cached.rows.length) {
        rowsSource = cached.rows;
        setAttrDraftAutoBuilt(false);
      } else if (!hasServerSaved && (rowsSource.length === 0 || (Array.isArray(data.suggested_rows) && (data.suggested_rows as AttrRow[]).length > rowsSource.length * 2))) {
        const learnedDraft = Array.isArray(data.suggested_rows) ? (data.suggested_rows as AttrRow[]) : [];
        const autoDraft = learnedDraft.length
          ? learnedDraft
          : buildDraftRowsFromYandexParams(
              data.providers?.yandex_market?.params,
              catalogAttrOptions || [],
              defs
            );
        if (autoDraft.length) {
          rowsSource = autoDraft;
          setAttrDraftAutoBuilt(true);
        } else {
          setAttrDraftAutoBuilt(false);
        }
      } else {
        setAttrDraftAutoBuilt(false);
      }
      const mergedBase = mergeRowsWithCatalogOptions(rowsSource, catalogAttrOptions || [], defs);
      const merged = alignRowsWithCatalogGroups(mergedBase, catalogAttrOptions || []);
      const withServiceRows = enforceServiceRowsTop(merged, defs);
      setAttrRows(applyYandexSystemBindings(withServiceRows, defs));
      setAttrCacheHydratedFor(categoryId);
    } catch (e) {
      setAttrDetails(null);
      setAttrRows([]);
      setAttrDetailsError((e as Error).message || "Ошибка загрузки категории");
    } finally {
      setAttrDetailsLoading(false);
    }
  }

  async function runBackgroundSync() {
    setSyncing(true);
    setSyncMsg("Обновление локального кэша...");
    try {
      categoriesMappingCache = { ts: 0, data: null };
      attrBootstrapCache = { ts: 0, data: null };
      attrDetailsCache.clear();
      await loadCategoriesMapping();
      if (mainTab === "import" && importTab === "features") {
        await loadAttrBootstrap();
      }
      setSyncMsg("Локальные данные обновлены");
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    (async () => {
      await loadInitialReadModel();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (mainTab !== "import" || importTab !== "features") return;
    loadAttrBootstrap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mainTab, importTab]);

  useEffect(() => {
    setAttrRows((prev) => {
      const merged = mergeRowsWithCatalogOptions(prev, catalogAttrOptions || [], serviceParamDefs);
      const aligned = alignRowsWithCatalogGroups(merged, catalogAttrOptions || []);
      const withServiceRows = enforceServiceRowsTop(aligned, serviceParamDefs);
      return applyYandexSystemBindings(withServiceRows, serviceParamDefs);
    });
  }, [serviceParamDefs, catalogAttrOptions]);

  useEffect(() => {
    if (mainTab !== "import" || importTab !== "features") return;
    if (!activeAttrCategoryId) return;
    if (useCatalogTreeForFeatures && selectedCatalogId && attrSelectedCategoryId !== selectedCatalogId) return;
    setAttrCacheHydratedFor("");
    loadAttrDetails(activeAttrCategoryId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeAttrCategoryId, attrSelectedCategoryId, selectedCatalogId, mainTab, importTab, useCatalogTreeForFeatures]);

  useEffect(() => {
    if (mainTab !== "import" || importTab !== "features") return;
    if (!activeAttrCategoryId) return;
    if (!attrRows.length) return;
    if (attrCacheHydratedFor !== activeAttrCategoryId) return;
    const timer = window.setTimeout(() => {
      const cache = loadAttrDraftCache();
      cache.byCategory[activeAttrCategoryId] = {
        rows: attrRows,
        updated_at: new Date().toISOString(),
      };
      saveAttrDraftCache(cache);
      setAttrDraftExists(true);
    }, 180);
    return () => window.clearTimeout(timer);
  }, [mainTab, importTab, activeAttrCategoryId, attrRows, attrCacheHydratedFor]);

  const displayProviders = useMemo<DisplayProvider[]>(() => {
    const byCode: Record<string, DisplayProvider> = {};
    for (const p of providers) byCode[p.code] = { ...p, connected: true };
    for (const [code, title] of Object.entries(PROVIDER_SLOTS)) {
      if (!byCode[code]) byCode[code] = { code, title, count: 0, connected: false };
    }
    return Object.values(byCode).sort((a, b) => a.title.localeCompare(b.title, "ru"));
  }, [providers]);

  const providerCategoryById = useMemo(() => {
    const out: Record<string, Record<string, ProviderCategory>> = {};
    for (const p of displayProviders) {
      const map: Record<string, ProviderCategory> = {};
      for (const c of providerCategories[p.code] || []) map[c.id] = c;
      out[p.code] = map;
    }
    return out;
  }, [displayProviders, providerCategories]);

  const nodeById = useMemo(() => {
    const m = new Map<string, CatalogNode>();
    for (const n of catalogNodes || []) m.set(n.id, n);
    return m;
  }, [catalogNodes]);
  const parentById = useMemo(() => {
    const m = new Map<string, string>();
    for (const n of catalogNodes || []) {
      if (n.parent_id) m.set(n.id, n.parent_id);
    }
    return m;
  }, [catalogNodes]);
  const pathById = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of catalogItems || []) m.set(c.id, c.path || c.name || "");
    return m;
  }, [catalogItems]);

  const childrenByParent = useMemo(() => {
    const m = new Map<string, CatalogNode[]>();
    for (const n of catalogNodes || []) {
      const pid = n.parent_id || "";
      const arr = m.get(pid) || [];
      arr.push(n);
      m.set(pid, arr);
    }
    for (const arr of m.values()) {
      arr.sort((a, b) => {
        if ((a.position || 0) !== (b.position || 0)) return (a.position || 0) - (b.position || 0);
        return (a.name || "").localeCompare(b.name || "", "ru");
      });
    }
    return m;
  }, [catalogNodes]);

  const treeSearchVisible = useMemo(() => {
    const q = qnorm(catalogQuery);
    if (!q) return null;
    const visible = new Set<string>();
    const markParents = (id: string) => {
      let cur = nodeById.get(id);
      const guard = new Set<string>();
      while (cur && !guard.has(cur.id)) {
        guard.add(cur.id);
        visible.add(cur.id);
        cur = cur.parent_id ? nodeById.get(cur.parent_id) : undefined;
      }
    };
    for (const n of catalogNodes || []) {
      if ((n.name || "").toLowerCase().includes(q)) markParents(n.id);
    }
    return visible;
  }, [catalogQuery, catalogNodes, nodeById]);

  const modalItems = useMemo(() => {
    const q = qnorm(modalQuery);
    const list = providerCategories[modalProvider] || [];
    if (!q) return list;
    return list.filter((x) => [x.path, x.name].join(" ").toLowerCase().includes(q));
  }, [providerCategories, modalProvider, modalQuery]);
  const modalItemsOrdered = useMemo(() => {
    const selected = String(modalSelectedProviderCategoryId || "").trim();
    if (!selected) return modalItems;
    const picked = modalItems.find((x) => x.id === selected);
    if (!picked) return modalItems;
    return [picked, ...modalItems.filter((x) => x.id !== selected)];
  }, [modalItems, modalSelectedProviderCategoryId]);
  const modalCatalogPath = useMemo(() => {
    if (!modalCatalogCategoryId) return "";
    const fromCatalogItems = catalogItems.find((x) => x.id === modalCatalogCategoryId)?.path || "";
    if (fromCatalogItems) return fromCatalogItems;
    return pathById.get(modalCatalogCategoryId) || "";
  }, [modalCatalogCategoryId, catalogItems, pathById]);

  const totalCategories = catalogItems.length;
  const mappedCount = useMemo(() => {
    if (!catalogItems.length) return 0;
    const providerCodes = displayProviders.map((p) => p.code).filter(Boolean);
    return catalogItems.filter((category) => {
      if (!providerCodes.length) return false;
      return providerCodes.some((providerCode) => leafCoverageState(category.id, providerCode) === "ok");
    }).length;
  }, [catalogItems, displayProviders, mappings, childrenByParent, parentById]);
  const unmappedCount = Math.max(0, totalCategories - mappedCount);

  const attrProviderParams = useMemo(() => {
    const out: Record<string, AttrParam[]> = {};
    for (const providerCode of MAPPING_PROVIDER_CODES) {
      const base = providerCode === "yandex_market" ? [...YANDEX_SYSTEM_TARGETS] : [];
      out[providerCode] = [...base, ...(attrDetails?.providers?.[providerCode]?.params || [])];
    }
    return out;
  }, [attrDetails]);

  const usedAttrParamIds = useMemo(() => {
    const out: Record<string, Set<string>> = Object.fromEntries(MAPPING_PROVIDER_CODES.map((code) => [code, new Set<string>()])) as Record<string, Set<string>>;
    for (const row of attrRows || []) {
      for (const providerCode of MAPPING_PROVIDER_CODES) {
        const item = row.provider_map?.[providerCode];
        if (item?.id) out[providerCode].add(String(item.id));
      }
    }
    return out;
  }, [attrRows]);

  const visibleProviderParams = useMemo(() => {
    const byProv: Record<string, AttrParam[]> = Object.fromEntries(MAPPING_PROVIDER_CODES.map((code) => [code, []])) as Record<string, AttrParam[]>;
    MAPPING_PROVIDER_CODES.forEach((providerCode) => {
      const items = (attrProviderParams[providerCode] || [])
        .filter((p) => !usedAttrParamIds[providerCode].has(String(p.id)))
        .sort((a, b) => String(a.name || "").localeCompare(String(b.name || ""), "ru"));
      byProv[providerCode] = items;
    });
    return byProv;
  }, [attrProviderParams, usedAttrParamIds]);

  const visibleProviderParamSections = useMemo(() => {
    const byProv: Record<string, Array<{ key: string; title: string; subtitle: string; items: AttrParam[] }>> =
      Object.fromEntries(MAPPING_PROVIDER_CODES.map((code) => [code, []])) as Record<string, Array<{ key: string; title: string; subtitle: string; items: AttrParam[] }>>;
    MAPPING_PROVIDER_CODES.forEach((providerCode) => {
      const items = visibleProviderParams[providerCode] || [];
      const systemItems = items.filter((item) => !!item.system);
      const categoryItems = items.filter((item) => !item.system);
      const sections: Array<{ key: string; title: string; subtitle: string; items: AttrParam[] }> = [];
      if (providerCode === "yandex_market") {
        sections.push({
          key: "system",
          title: "Системные поля Я.Маркета",
          subtitle: "Поля payload канала: offerId, name, vendor, description, pictures, barcode.",
          items: systemItems,
        });
      }
      sections.push({
        key: "category",
        title: providerCode === "yandex_market" ? "Параметры категории Я.Маркета" : "Параметры категории Ozon",
        subtitle: providerCode === "yandex_market" ? "Поля шаблона категории, пришедшие из API Я.Маркета." : "Поля шаблона категории, пришедшие из API Ozon.",
        items: providerCode === "yandex_market" ? categoryItems : items,
      });
      byProv[providerCode] = sections;
    });
    return byProv;
  }, [visibleProviderParams]);

  const providerParamStats = useMemo(() => {
    const out: Record<string, { total: number; visible: number; hiddenUsed: number }> =
      Object.fromEntries(MAPPING_PROVIDER_CODES.map((code) => [code, { total: 0, visible: 0, hiddenUsed: 0 }])) as Record<string, { total: number; visible: number; hiddenUsed: number }>;
    MAPPING_PROVIDER_CODES.forEach((providerCode) => {
      const total = (attrProviderParams[providerCode] || []).length;
      const visible = (visibleProviderParams[providerCode] || []).length;
      out[providerCode] = { total, visible, hiddenUsed: Math.max(0, total - visible) };
    });
    return out;
  }, [attrProviderParams, visibleProviderParams]);

  const mappingProvidersForUi = useMemo(
    () => MAPPING_PROVIDER_CODES.filter((code) => !!PROVIDER_SLOTS[code]),
    []
  );

  const catalogNameSuggests = useMemo(() => {
    const names = new Set<string>();
    for (const s of serviceParamDefs) names.add(s.title);
    for (const a of catalogAttrOptions || []) {
      const t = String(a.title || "").trim();
      if (t) names.add(t);
    }
    for (const r of attrRows || []) {
      const t = String(r.catalog_name || "").trim();
      if (t) names.add(t);
    }
    return Array.from(names).sort((a, b) => a.localeCompare(b, "ru"));
  }, [catalogAttrOptions, attrRows]);

  function openModal(catalogCategoryId: string, providerCode: string, initialProviderCategoryId = "") {
    applySelectedCatalogId(catalogCategoryId);
    setModalCatalogCategoryId(catalogCategoryId);
    setModalProvider(providerCode);
    setModalSelectedProviderCategoryId(initialProviderCategoryId || "");
    setModalQuery("");
    setModalOpen(true);
  }

  function splitPath(path: string) {
    const parts = (path || "").split(" / ").filter(Boolean);
    const node = parts[parts.length - 1] || path;
    const crumbs = parts.slice(0, -1).join(" / ");
    return { node, crumbs };
  }

  const hasExpandedNodes = useMemo(
    () =>
      Object.entries(treeExpanded).some(
        ([id, value]) => value && (childrenByParent.get(id) || []).length > 0
      ),
    [childrenByParent, treeExpanded]
  );

  function isTreeNodeVisible(nodeId: string) {
    if (!treeSearchVisible) return true;
    return treeSearchVisible.has(nodeId);
  }

  useEffect(() => {
    if (selectedCatalogId) return;
    const firstVisibleRoot = (childrenByParent.get("") || []).find((node) => isTreeNodeVisible(node.id));
    if (firstVisibleRoot?.id) applySelectedCatalogId(firstVisibleRoot.id);
  }, [childrenByParent, treeSearchVisible, selectedCatalogId]);

  useEffect(() => {
    if (mainTab !== "import" || importTab !== "features" || !useCatalogTreeForFeatures) return;
    if (!selectedCatalogId) return;
    if (attrSelectedCategoryId === selectedCatalogId) return;
    setAttrSelectedCategoryId(selectedCatalogId);
  }, [mainTab, importTab, useCatalogTreeForFeatures, selectedCatalogId, attrSelectedCategoryId]);

  useEffect(() => {
    if (!selectedCatalogId) return;
    setTreeExpanded((prev) => {
      const nextExpanded: Record<string, boolean> = {};
      let cur = parentById.get(selectedCatalogId) || "";
      const guard = new Set<string>();
      while (cur && !guard.has(cur)) {
        guard.add(cur);
        if (!prev[cur]) nextExpanded[cur] = true;
        cur = parentById.get(cur) || "";
      }
      if (!Object.keys(nextExpanded).length) return prev;
      return { ...prev, ...nextExpanded };
    });
  }, [selectedCatalogId, parentById]);

  function toggleTreeNode(nodeId: string) {
    setTreeExpanded((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
  }

  function revealCatalogNode(nodeId: string) {
    const nextExpanded: Record<string, boolean> = {};
    let cur = parentById.get(nodeId) || "";
    const guard = new Set<string>();
    while (cur && !guard.has(cur)) {
      guard.add(cur);
      nextExpanded[cur] = true;
      cur = parentById.get(cur) || "";
    }
    if (Object.keys(nextExpanded).length) {
      setTreeExpanded((prev) => ({ ...prev, ...nextExpanded }));
    }
    applySelectedCatalogId(nodeId);
  }

  function renderCatalogTreeRows(node: CatalogNode, level: number): ReactNode {
    if (!isTreeNodeVisible(node.id)) return null;
    const children = (childrenByParent.get(node.id) || []).filter((x) => isTreeNodeVisible(x.id));
    const hasChildren = children.length > 0;
    const expanded = qnorm(catalogQuery) ? true : !!treeExpanded[node.id];
    const isSelected = selectedCatalogId === node.id;
    return (
      <div key={node.id}>
        <div className="csb-treeRow" style={{ ["--depth" as any]: level }}>
          <div
            className={`csb-treeNode ${isSelected ? "is-active" : ""}`}
            onClick={() => applySelectedCatalogId(node.id)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                applySelectedCatalogId(node.id);
              }
            }}
          >
            {hasChildren ? (
              <button
                type="button"
                className="csb-caretBtn"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleTreeNode(node.id);
                }}
                title={expanded ? "Свернуть" : "Развернуть"}
              >
                {expanded ? "▾" : "▸"}
              </button>
            ) : (
              <span className="csb-caretSpacer" aria-hidden="true" />
            )}
            <span className="csb-treeName" title={node.name}>{node.name}</span>
            <span className="csb-treeCount" />
          </div>
        </div>
        {hasChildren && expanded ? children.map((child) => renderCatalogTreeRows(child, level + 1)) : null}
      </div>
    );
  }

  function nearestMappedAncestor(nodeId: string, providerCode: string): string {
    let cur = parentById.get(nodeId) || "";
    const guard = new Set<string>();
    while (cur && !guard.has(cur)) {
      guard.add(cur);
      if (String(mappings[cur]?.[providerCode] || "").trim()) return cur;
      cur = parentById.get(cur) || "";
    }
    return "";
  }

  function effectiveProviderCategoryId(nodeId: string, providerCode: string): string {
    const direct = String(mappings[nodeId]?.[providerCode] || "").trim();
    if (direct) return direct;
    const anc = nearestMappedAncestor(nodeId, providerCode);
    return anc ? String(mappings[anc]?.[providerCode] || "").trim() : "";
  }

  function descendantDirectBindings(nodeId: string, providerCode: string): Array<{
    providerCategoryId: string;
    providerCategory: ProviderCategory | null;
    catalogIds: string[];
    catalogPaths: string[];
  }> {
    const grouped = new Map<string, { providerCategoryId: string; providerCategory: ProviderCategory | null; catalogIds: string[]; catalogPaths: string[] }>();
    const stack = [...(childrenByParent.get(nodeId) || [])];
    const seen = new Set<string>();
    while (stack.length) {
      const cur = String(stack.pop() || "");
      if (!cur || seen.has(cur)) continue;
      seen.add(cur);
      const directId = String(mappings[cur]?.[providerCode] || "").trim();
      if (directId) {
        const existing = grouped.get(directId) || {
          providerCategoryId: directId,
          providerCategory: providerCategoryById[providerCode]?.[directId] || null,
          catalogIds: [],
          catalogPaths: [],
        };
        existing.catalogIds.push(cur);
        existing.catalogPaths.push(pathById.get(cur) || cur);
        grouped.set(directId, existing);
      }
      stack.push(...(childrenByParent.get(cur) || []));
    }
    return Array.from(grouped.values()).sort((a, b) =>
      String(a.providerCategory?.path || a.providerCategory?.name || a.providerCategoryId).localeCompare(
        String(b.providerCategory?.path || b.providerCategory?.name || b.providerCategoryId),
        "ru"
      )
    );
  }

  function leafCoverageState(nodeId: string, providerCode: string): "ok" | "warn" | "none" {
    const children = childrenByParent.get(nodeId) || [];
    const directOrInherited = !!effectiveProviderCategoryId(nodeId, providerCode);
    if (directOrInherited) return "ok";
    if (!children.length) return "none";

    let totalLeaves = 0;
    let mappedLeaves = 0;
    const stack = [...children];
    while (stack.length) {
      const cur = stack.pop() as CatalogNode;
      const ch = childrenByParent.get(cur.id) || [];
      if (!ch.length) {
        totalLeaves += 1;
        if (effectiveProviderCategoryId(cur.id, providerCode)) mappedLeaves += 1;
      } else {
        stack.push(...ch);
      }
    }
    if (totalLeaves === 0) return "none";
    if (mappedLeaves === 0) return "none";
    if (mappedLeaves === totalLeaves) return "ok";
    return "warn";
  }

  async function saveLinkFor(catalogCategoryId: string, providerCode: string, providerCategoryId: string | null, closeModal = false) {
    if (!catalogCategoryId || !providerCode) return;
    setSaving(true);
    setErr(null);
    try {
      const res = await api<LinkResp>("/marketplaces/mapping/import/categories/link", {
        method: "POST",
        body: JSON.stringify({
          catalog_category_id: catalogCategoryId,
          provider: providerCode,
          provider_category_id: providerCategoryId,
        }),
      });
      setMappings(res.mappings || {});
      if (importTab === "features") {
        await loadAttrBootstrap().catch(() => null);
      }
      if (closeModal) setModalOpen(false);
      setSavedToastText("Сопоставление сохранено");
      setSavedToast(true);
    } catch (e) {
      const raw = (e as Error).message || "Ошибка сохранения связи";
      if (raw.includes("DESCENDANT_BINDINGS_EXIST")) {
        setErr("У этой категории есть собственные привязки в дочерних ветках. Сначала очистите дочерние привязки, затем задайте общую.");
      } else {
        setErr(raw);
      }
    } finally {
      setSaving(false);
    }
  }

  function openClearDescendantsModal(catalogCategoryId: string, providerCode: string) {
    setClearModalCategoryId(catalogCategoryId);
    setClearModalProvider(providerCode);
    setClearModalPreserveTemplates(true);
    setClearModalOpen(true);
  }

  async function clearDescendantBindingsAndContinue() {
    if (!clearModalCategoryId || !clearModalProvider) return;
    setSaving(true);
    setErr(null);
    try {
      const res = await api<ClearDescendantBindingsResp>("/marketplaces/mapping/import/categories/clear-descendants", {
        method: "POST",
        body: JSON.stringify({
          catalog_category_id: clearModalCategoryId,
          provider: clearModalProvider,
          preserve_templates: clearModalPreserveTemplates,
        }),
      });
      setMappings(res.mappings || {});
      setClearModalOpen(false);
      const preservedCount = Number((res.preserved_template_category_ids || []).length || 0);
      setSavedToastText(
        preservedCount
          ? `Дочерние привязки очищены. Шаблоны сохранены: ${preservedCount}`
          : "Дочерние привязки очищены"
      );
      setSavedToast(true);
      openModal(clearModalCategoryId, clearModalProvider, "");
    } catch (e) {
      setErr((e as Error).message || "Ошибка очистки дочерних привязок");
    } finally {
      setSaving(false);
    }
  }

  async function saveLink(providerCategoryId: string | null) {
    if (!modalCatalogCategoryId || !modalProvider) return;
    await saveLinkFor(modalCatalogCategoryId, modalProvider, providerCategoryId, true);
  }
  async function saveModalSelection() {
    const selected = String(modalSelectedProviderCategoryId || "").trim();
    await saveLink(selected || null);
  }

  useEffect(() => {
    if (!savedToast) return;
    const t = window.setTimeout(() => setSavedToast(false), 2200);
    return () => window.clearTimeout(t);
  }, [savedToast]);

  function addAttrRow() {
    if (!attrEditMode) return;
    const id = `row_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    setPendingScrollFocus(true);
    setPendingScrollRowId(id);
    setAttrRows((prev) =>
      enforceServiceRowsTop([
        ...prev,
        {
          id,
          catalog_name: "",
          group: "О товаре",
          provider_map: defaultProviderMap(),
          confirmed: false,
        },
      ], serviceParamDefs)
    );
  }

  useEffect(() => {
    if (!pendingScrollRowId) return;
    const timer = window.setTimeout(() => {
      const anchor = document.getElementById(`attr-row-anchor-${pendingScrollRowId}`);
      if (!anchor) return;
      anchor.scrollIntoView({ behavior: "smooth", block: "center" });
      if (pendingScrollFocus) {
        const input = anchor.querySelector("input");
        if (input instanceof HTMLInputElement) input.focus();
      }
      setPendingScrollRowId("");
      setPendingScrollFocus(false);
    }, 40);
    return () => window.clearTimeout(timer);
  }, [pendingScrollFocus, pendingScrollRowId, attrRows]);

  function updateAttrRow(rowId: string, patch: Partial<AttrRow>) {
    if (!attrEditMode) return;
    if (Object.prototype.hasOwnProperty.call(patch, "group")) {
      setPendingScrollFocus(false);
      setPendingScrollRowId(rowId);
    }
    setAttrRows((prev) =>
      enforceServiceRowsTop(
        prev.map((r) => {
          if (r.id !== rowId) return r;
          const next = { ...r, ...patch };
          next.group = normalizeParamGroup(next.group, next.catalog_name);
          return next;
        }),
        serviceParamDefs
      )
    );
  }

  function setAllRowsConfirmed(checked: boolean) {
    if (!attrEditMode) return;
    setAttrRows((prev) =>
      enforceServiceRowsTop(
        prev.map((r) => ({ ...r, confirmed: checked })),
        serviceParamDefs
      )
    );
  }

  function removeAttrRow(rowId: string) {
    if (!attrEditMode) return;
    if (String(rowId).startsWith("svc:")) return;
    setAttrRows((prev) => enforceServiceRowsTop(prev.filter((r) => r.id !== rowId), serviceParamDefs));
  }

function setAttrProviderValue(rowId: string, provider: string, value: AttrRowProviderMap) {
    if (!attrEditMode) return;
    setAttrRows((prev) =>
      enforceServiceRowsTop(
        prev.map((r) => {
          if (r.id !== rowId) return r;
          return {
            ...r,
            provider_map: {
              ...(r.provider_map || {}),
              [provider]: value,
            },
            catalog_name: r.catalog_name || value.name || "",
            group: normalizeParamGroup(r.group, r.catalog_name || value.name || ""),
          };
        }),
        serviceParamDefs
      )
    );
  }

  function clearAttrProviderValue(rowId: string, provider: string) {
    setAttrProviderValue(rowId, provider, {
      id: "",
      name: "",
      kind: "",
      values: [],
      required: false,
      export: false,
    });
  }

  function onDragParam(provider: string, param: AttrParam, e: DragEvent) {
    if (!attrEditMode) {
      e.preventDefault();
      return;
    }
    const dragKey = `${provider}:${String(param.id || "")}`;
    setDragParamKey(dragKey);
    setDragProvider(provider);
    e.dataTransfer.setData(
      "application/x-market-param",
      JSON.stringify({
        provider,
        id: String(param.id || ""),
        name: String(param.name || ""),
        kind: String(param.kind || ""),
        values: Array.isArray(param.values) ? param.values : [],
        required: !!param.required,
      })
    );
    e.dataTransfer.effectAllowed = "copy";
  }

  function onDragEndParam() {
    setDragParamKey("");
    setDragProvider("");
    setDropCellKey("");
  }

  function onDropParam(rowId: string, provider: string, e: DragEvent) {
    if (!attrEditMode) {
      e.preventDefault();
      return;
    }
    if (dragProvider && dragProvider !== provider) {
      setDropCellKey("");
      return;
    }
    e.preventDefault();
    setDropCellKey("");
    const raw = e.dataTransfer.getData("application/x-market-param");
    if (!raw) return;
    try {
      const p = JSON.parse(raw);
      if (!p || String(p.provider || "") !== provider) return;
      setAttrProviderValue(rowId, provider, {
        id: String(p.id || ""),
        name: String(p.name || ""),
        kind: String(p.kind || ""),
        values: Array.isArray(p.values) ? p.values : [],
        required: !!p.required,
        export: true,
      });
    } catch {
      // ignore
    } finally {
      setDragParamKey("");
      setDragProvider("");
    }
  }

  function valuesText(values?: string[]) {
    if (!Array.isArray(values) || values.length === 0) return "Без справочника значений";
    return values.slice(0, 8).join(", ");
  }

  async function saveAttrRows() {
    if (!activeAttrCategoryId) return;
    if (!attrEditMode) return;
    setAttrSaving(true);
    try {
      const selectedItem = (attrCategories || []).find((x) => x.id === activeAttrCategoryId);
      const applyTo = (selectedItem?.group_category_ids || []).filter((x) => x && x !== activeAttrCategoryId);
      const resp = await api<AttrSaveResp>(`/marketplaces/mapping/import/attributes/${encodeURIComponent(activeAttrCategoryId)}`, {
        method: "PUT",
        body: JSON.stringify({ rows: attrRows, apply_to_category_ids: applyTo }),
      });
      const cache = loadAttrDraftCache();
      cache.byCategory[activeAttrCategoryId] = {
        rows: attrRows,
        updated_at: new Date().toISOString(),
      };
      saveAttrDraftCache(cache);
      setAttrDraftExists(true);
      setSavedTemplateId(String(resp.template_id || ""));
      await loadAttrBootstrap();
      await loadAttrDetails(activeAttrCategoryId);
      setAttrHasServerSaved(true);
      setAttrEditMode(false);
      setSavedToast(true);
    } finally {
      setAttrSaving(false);
    }
  }

  async function runAiMatch() {
    if (!activeAttrCategoryId) return;
    if (!attrEditMode) return;
    setAttrAiMatching(true);
    setErr(null);
    try {
      const res = await api<AttrAiMatchResp>(
        `/marketplaces/mapping/import/attributes/${encodeURIComponent(activeAttrCategoryId)}/ai-match`,
        {
          method: "POST",
          body: JSON.stringify({ apply: true }),
        }
      );
      setAttrRows(enforceServiceRowsTop(res.rows || [], serviceParamDefs));
      await loadAttrBootstrap();
      await loadAttrDetails(activeAttrCategoryId);
      setSyncMsg(`AI-сопоставление выполнено (${res.engine === "ollama" ? "Ollama" : "fallback"})`);
    } catch (e) {
      setErr((e as Error).message || "Ошибка AI-сопоставления");
    } finally {
      setAttrAiMatching(false);
    }
  }

  const selectedCatalogNode = useMemo(() => {
    if (!selectedCatalogId) return null;
    return catalogNodes.find((node) => node.id === selectedCatalogId) || null;
  }, [catalogNodes, selectedCatalogId]);

  const groupedAttrRows = useMemo(() => {
    const query = qnorm(attrRowQuery);
    const byGroup: Record<ParamGroup, AttrRow[]> = {
      "Артикулы": [],
      "Описание": [],
      "Медиа": [],
      "О товаре": [],
      "Логистика": [],
      "Гарантия": [],
      "Прочее": [],
    };
    for (const row of attrRows || []) {
      const service = isServiceRow(row, serviceParamDefs);
      if (attrTemplateTab === "base" && !service) continue;
      if (attrTemplateTab === "category" && service) continue;
      const providerBindings = mappingProvidersForUi.filter((providerCode) => {
        const value = row.provider_map?.[providerCode];
        return !!String(value?.id || "").trim();
      }).length;
      const isUnmapped = providerBindings === 0;
      const needsAttention = !row.confirmed || isUnmapped;
      if (attrRowFilter === "ready" && !row.confirmed) continue;
      if (attrRowFilter === "attention" && !needsAttention) continue;
      if (attrRowFilter === "unmapped" && !isUnmapped) continue;
      if (query) {
        const haystack = [
          row.catalog_name || "",
          row.group || "",
          ...mappingProvidersForUi.flatMap((providerCode) => {
            const value = row.provider_map?.[providerCode];
            return [value?.name || "", value?.kind || "", ...(Array.isArray(value?.values) ? value!.values : [])];
          }),
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(query)) continue;
      }
      const g = normalizeParamGroup(row.group, row.catalog_name);
      byGroup[g].push({ ...row, group: g });
    }
    for (const g of PARAM_GROUPS) {
      byGroup[g].sort((a, b) => String(a.catalog_name || "").localeCompare(String(b.catalog_name || ""), "ru"));
    }
    return PARAM_GROUPS.map((g) => ({ group: g, rows: byGroup[g] })).filter((x) => x.rows.length > 0);
  }, [attrRows, attrTemplateTab, serviceParamDefs, attrRowFilter, attrRowQuery, mappingProvidersForUi]);

  const attrBaseRowsCount = useMemo(
    () => (attrRows || []).filter((row) => isServiceRow(row, serviceParamDefs)).length,
    [attrRows, serviceParamDefs]
  );
  const attrCategoryRowsCount = useMemo(
    () => (attrRows || []).filter((row) => !isServiceRow(row, serviceParamDefs)).length,
    [attrRows, serviceParamDefs]
  );

  const allRowsConfirmed = useMemo(() => {
    if (!attrRows.length) return false;
    return attrRows.every((r) => !!r.confirmed);
  }, [attrRows]);

  const attrRowsStats = useMemo(() => {
    let ready = 0;
    let unmapped = 0;
    let attention = 0;
    for (const row of attrRows || []) {
      const providerBindings = mappingProvidersForUi.filter((providerCode) => !!String(row.provider_map?.[providerCode]?.id || "").trim()).length;
      const isUnmapped = providerBindings === 0;
      const needsAttention = !row.confirmed || isUnmapped;
      if (row.confirmed) ready += 1;
      if (isUnmapped) unmapped += 1;
      if (needsAttention) attention += 1;
    }
    return {
      total: attrRows.length,
      ready,
      unmapped,
      attention,
      visible: groupedAttrRows.reduce((sum, section) => sum + section.rows.length, 0),
    };
  }, [attrRows, mappingProvidersForUi, groupedAttrRows]);

  function clearAttrDraft() {
    if (!activeAttrCategoryId) return;
    const cache = loadAttrDraftCache();
      if (cache.byCategory[activeAttrCategoryId]) {
        delete cache.byCategory[activeAttrCategoryId];
        saveAttrDraftCache(cache);
      }
      setAttrDraftExists(false);
    loadAttrDetails(activeAttrCategoryId);
  }

  return (
    <div className={`mm-wrap mm-page ${embedded ? "isEmbedded" : ""}`}>
      {!embedded ? (
        <div className="mm-header">
          <div className="mm-headerMain">
            <div className="mm-h1">Маппинг источников</div>
            <div className="mm-sub">Категории маркетплейсов и сопоставление параметров с каталогом PIM.</div>
          </div>

          <div className="mm-headerActions">
            <button className="btn mm-syncBtn" type="button" onClick={runBackgroundSync} disabled={loading || syncing}>
              {syncing ? "Синхронизация..." : "Обновить"}
            </button>
            <Link className="btn" to="/">← На главную</Link>
          </div>
        </div>
      ) : null}

      {!embedded ? (
        <div className="mm-statusBar">
          <span className={`mm-dot ${syncing ? "isRun" : ""}`} />
          <span>{syncMsg || (syncing ? "Синхронизация в фоне..." : "Готово")}</span>
        </div>
      ) : null}

      {err && (
        <div className="card" style={{ marginBottom: 12 }}>
          <div style={{ color: "#b42318", fontWeight: 700 }}>{err}</div>
        </div>
      )}

      {!hideMainTabs && !forcedMainTab && (
        <div className="mm-tabs">
          <button className={`mm-tab ${mainTab === "import" ? "active" : ""}`} onClick={() => setMainTab("import")}>Импорт</button>
          <button className={`mm-tab ${mainTab === "export" ? "active" : ""}`} onClick={() => setMainTab("export")}>Экспорт</button>
        </div>
      )}

      {mainTab === "import" ? (
        <>
          {!hideImportTabs && !forcedImportTab && (
            <div className="mm-tabs">
              <button className={`mm-tab ${importTab === "categories" ? "active" : ""}`} onClick={() => setImportTab("categories")}>Категории</button>
              <button className={`mm-tab ${importTab === "features" ? "active" : ""}`} onClick={() => setImportTab("features")}>Параметры</button>
            </div>
          )}

          {importTab === "categories" ? (
            <div className="card mm-card">
              <div className="mm-summaryCard">
                <div className="mm-summaryHead">
                  <div className="mm-summaryTitleBlock">
                    <div className="mm-title">Сводка</div>
                    <div className="muted">Покрытие дерева категорий и состояние подключенных площадок.</div>
                  </div>
                  <button className="btn mm-miniBtn mm-syncBtn" type="button" onClick={runBackgroundSync} disabled={loading || syncing}>
                    {syncing ? "Синхронизация..." : "Обновить"}
                  </button>
                </div>

                <div className="mm-kpis">
                  <div className="mm-kpi">
                    <div className="mm-kpiLabel">Количество категорий</div>
                    <div className="mm-kpiValue">{totalCategories}</div>
                  </div>
                  <div className="mm-kpi">
                    <div className="mm-kpiLabel">Сопоставлено / Не сопоставлено</div>
                    <div className="mm-kpiValue">
                      {mappedCount} <span className="mm-kpiSep">/</span> {unmappedCount}
                    </div>
                  </div>
                  {displayProviders.map((p) => (
                    <div key={`kpi-${p.code}`} className="mm-kpi">
                      <div className="mm-kpiLabel">{p.title}</div>
                      <div className="mm-kpiValue">{p.connected ? p.count : 0}</div>
                      <div className="mm-kpiMeta">
                        {p.connected ? "категорий на площадке" : "не подключено"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mm-workbenchBlock">
              <div className="mm-head mm-headWorkspace">
                <div>
                  <div className="mm-title">Сопоставление категорий и конкурентов</div>
                  <div className="muted">Добавляйте сопоставления на любом уровне дерева. Наследование применяется только вниз.</div>
                </div>
                <div className="mm-tools">
                  <input className="pn-input" placeholder="Поиск по каталогу..." value={catalogQuery} onChange={(e) => setCatalogQuery(e.target.value)} />
                </div>
              </div>

              <div className="muted mm-note">
                Выберите категорию слева, затем сопоставляйте площадки и ссылки конкурентов справа.
              </div>

              {!displayProviders.length ? (
                <div className="empty-state">Нет площадок для сопоставления.</div>
              ) : (
                <div className="mm-workspace">
                  <CategorySidebar
                    className="mm-treePane mm-treePaneShared"
                    title="Каталог"
                    hint="Структура каталога"
                    searchValue={catalogQuery}
                    onSearchChange={setCatalogQuery}
                    searchPlaceholder="Быстрый поиск"
                    controls={
                      <button className="btn sm" type="button" onClick={hasExpandedNodes ? () => setTreeExpanded({}) : () => {
                        const next: Record<string, boolean> = {};
                        for (const [parentId, children] of childrenByParent.entries()) {
                          if (parentId && children.length > 0) next[parentId] = true;
                        }
                        setTreeExpanded(next);
                      }}>
                        {hasExpandedNodes ? "Свернуть" : "Развернуть"}
                      </button>
                    }
                  >
                    <div className="csb-tree">
                      {(childrenByParent.get("") || []).filter((n) => isTreeNodeVisible(n.id)).map((root) => renderCatalogTreeRows(root, 0))}
                    </div>
                  </CategorySidebar>

                  <div className="mm-detailPane">
                    <div className="mm-paneHead">
                      <div>
                        <div className="mm-paneTitle">{selectedCatalogNode ? selectedCatalogNode.name : "Категория"}</div>
                      </div>
                    </div>

                    {selectedCatalogNode ? (
                      <>
                        <div className={`mm-detailContent ${renderCategoryDetailExtra ? "hasExtra" : ""}`}>
                          <div className="mm-detailMain">
                            <div className="mm-providerStack">
                              {displayProviders.map((prov) => {
                                const stateInfo = bindingStates?.[selectedCatalogNode.id]?.[prov.code];
                                const directId = String(stateInfo?.direct_id || mappings[selectedCatalogNode.id]?.[prov.code] || "").trim();
                                const inheritedFrom = String(
                                  stateInfo?.inherited_from || (directId ? "" : nearestMappedAncestor(selectedCatalogNode.id, prov.code)) || ""
                                ).trim();
                                const childBindings = (
                                  stateInfo?.child_bindings?.map((binding) => ({
                                    providerCategoryId: String(binding.provider_category_id || "").trim(),
                                    providerCategory:
                                      providerCategoryById[prov.code]?.[String(binding.provider_category_id || "").trim()] ||
                                      (binding.provider_category_name
                                        ? {
                                            id: String(binding.provider_category_id || "").trim(),
                                            name: String(binding.provider_category_name || "").trim(),
                                            path: String(binding.provider_category_name || "").trim(),
                                            is_leaf: true,
                                          }
                                        : null),
                                    catalogIds: binding.catalog_ids || [],
                                    catalogPaths: binding.catalog_paths || [],
                                  })) || (directId ? [] : descendantDirectBindings(selectedCatalogNode.id, prov.code))
                                );
                                const effectiveId = String(
                                  stateInfo?.effective_id ||
                                  directId ||
                                  (inheritedFrom ? String(mappings[inheritedFrom]?.[prov.code] || "").trim() : "") ||
                                  ""
                                ).trim();
                                const canOpen = prov.connected || !!PROVIDER_SLOTS[prov.code];
                                const canEdit = canOpen && !!directId;
                                const canDelete = !!directId;
                                const aggregatedFromChildren = childBindings.length > 0;
                                const inheritedOnly = !directId && !aggregatedFromChildren && !!inheritedFrom;
                                const mainLabel = canEdit ? "Изменить" : inheritedOnly ? "Задать свою" : "Сопоставить";
                                const mainDisabled = !canOpen;
                                const mappedCat = effectiveId ? providerCategoryById[prov.code]?.[effectiveId] : null;
                                const mp = splitPath(mappedCat?.path || mappedCat?.name || "");
                                const statusLabel = directId
                                  ? "Связано"
                                  : aggregatedFromChildren
                                    ? "Из дочерних категорий"
                                    : inheritedOnly
                                      ? "Наследуется"
                                      : "Не сопоставлено";
                                return (
                                  <div key={`${selectedCatalogNode.id}-${prov.code}-detail`} className="mm-providerDetailCard">
                                    <div className="mm-providerDetailHead">
                                      <div className="mm-providerLead">
                                        <div className="mm-lineProvider">{prov.title}</div>
                                        <div className={`mm-providerState ${directId ? "isOwn" : aggregatedFromChildren || inheritedOnly ? "isInherit" : "isEmpty"}`}>
                                          {statusLabel}
                                        </div>
                                      </div>
                                    </div>
                                    <div className="mm-providerActionsBar">
                                      <div className="mm-providerActionBtns">
                                        <button
                                          className="btn mm-miniBtn mm-actBtn"
                                          type="button"
                                          onClick={() => {
                                            if (aggregatedFromChildren) {
                                              openClearDescendantsModal(selectedCatalogNode.id, prov.code);
                                              return;
                                            }
                                            openModal(selectedCatalogNode.id, prov.code, effectiveId);
                                          }}
                                          disabled={mainDisabled}
                                        >
                                          {mainLabel}
                                        </button>
                                        {aggregatedFromChildren ? (
                                          <button
                                            className="btn mm-miniBtn mm-ghostBtn"
                                            type="button"
                                            onClick={() => openClearDescendantsModal(selectedCatalogNode.id, prov.code)}
                                            disabled={saving}
                                          >
                                            Очистить
                                          </button>
                                        ) : null}
                                        {canDelete ? (
                                          <button
                                            className="btn mm-miniBtn mm-ghostBtn"
                                            type="button"
                                            onClick={() => {
                                              void saveLinkFor(selectedCatalogNode.id, prov.code, null);
                                            }}
                                            disabled={saving}
                                          >
                                            Снять
                                          </button>
                                        ) : null}
                                      </div>
                                    </div>
                                    <div className="mm-lineContent">
                                      {aggregatedFromChildren ? (
                                        <div className="mm-aggList">
                                          {inheritedOnly && mappedCat ? (
                                            <div className="mm-aggNotice">
                                              Базовая привязка наследуется от родителя: <strong>{splitPath(pathById.get(inheritedFrom) || inheritedFrom).node}</strong>
                                            </div>
                                          ) : null}
                                          {childBindings.map((binding) => {
                                            const pathInfo = splitPath(binding.providerCategory?.path || binding.providerCategory?.name || binding.providerCategoryId);
                                            return (
                                              <div key={`${prov.code}-${binding.providerCategoryId}`} className="mm-aggItem">
                                                <div className="mm-aggItemMain">
                                                  <div className="mm-providerPath">{pathInfo.node}</div>
                                                  {pathInfo.crumbs ? <div className="mm-breadcrumbs">{pathInfo.crumbs}</div> : null}
                                                  <div className="mm-aggChildren">
                                                    {binding.catalogIds.map((catalogId, idx) => (
                                                      <button
                                                        key={`${binding.providerCategoryId}-${catalogId}`}
                                                        type="button"
                                                        className="mm-aggLink"
                                                        onClick={() => revealCatalogNode(catalogId)}
                                                      >
                                                        {splitPath(binding.catalogPaths[idx] || catalogId).node}
                                                      </button>
                                                    ))}
                                                  </div>
                                                </div>
                                              </div>
                                            );
                                          })}
                                          <div className="mm-lineEmpty">
                                            Привязки заданы в дочерних категориях. Из родительской категории их можно только просматривать или очистить перед новой общей привязкой.
                                          </div>
                                        </div>
                                      ) : mappedCat ? (
                                        <>
                                          <div className="mm-providerPath">{mp.node}</div>
                                          {mp.crumbs ? <div className="mm-breadcrumbs">{mp.crumbs}</div> : null}
                                          {inheritedOnly && inheritedFrom ? (
                                            <button type="button" className="mm-aggLink" onClick={() => revealCatalogNode(inheritedFrom)}>
                                              Перейти к родительской категории
                                            </button>
                                          ) : null}
                                        </>
                                      ) : (
                                        <div className="mm-lineEmpty">Категория площадки пока не связана с выбранной категорией.</div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          {renderCategoryDetailExtra ? (
                            <div className="mm-detailSide">
                              <div className="mm-categoryExtra mm-categoryExtraSide">
                                {renderCategoryDetailExtra(selectedCatalogNode.id, selectedCatalogNode.name)}
                              </div>
                            </div>
                          ) : null}
                        </div>
                      </>
                    ) : (
                      <div className="mm-emptyWorkspace">Выберите категорию слева, чтобы работать с сопоставлениями площадок.</div>
                    )}
                  </div>
                </div>
              )}
              </div>
            </div>
          ) : (
            <div className="card mm-card">
              <div className="mm-title" style={{ marginBottom: 6 }}>Параметры</div>
              <div className="muted" style={{ marginBottom: 12 }}>
                Слева выберите сопоставленную категорию. Справа перетаскивайте параметры площадок в строки мастер-шаблона и подтверждайте чекбоксом.
              </div>

              <div className="mm-attrLayout">
                <div className="mm-attrLeft">
                  <div className="mm-attrLeftHead">
                    <div className="card-title">Категории</div>
                    <div className="muted">{useCatalogTreeForFeatures ? catalogItems.length : attrCategories.length}</div>
                  </div>
                  {useCatalogTreeForFeatures ? (
                    <CategorySidebar
                      className="mm-treePaneShared mm-treePaneFeatures"
                      title="Категории"
                      hint="Структура каталога"
                      searchValue={catalogQuery}
                      onSearchChange={setCatalogQuery}
                      searchPlaceholder="Быстрый поиск"
                      controls={
                        <button className="btn sm" type="button" onClick={hasExpandedNodes ? () => setTreeExpanded({}) : () => {
                          const next: Record<string, boolean> = {};
                          for (const [parentId, children] of childrenByParent.entries()) {
                            if (parentId && children.length > 0) next[parentId] = true;
                          }
                          setTreeExpanded(next);
                        }}>
                          {hasExpandedNodes ? "Свернуть" : "Развернуть"}
                        </button>
                      }
                    >
                      <div className="csb-tree">
                        {(childrenByParent.get("") || []).filter((n) => isTreeNodeVisible(n.id)).map((root) => renderCatalogTreeRows(root, 0))}
                      </div>
                    </CategorySidebar>
                  ) : attrCategoriesLoading ? (
                    <div className="muted">Загрузка...</div>
                  ) : attrCategories.length === 0 ? (
                    <div className="muted">Нет сопоставленных категорий.</div>
                  ) : (
                    <div className="mm-attrCatList">
                      {attrCategories.map((c) => {
                        const active = activeAttrCategoryId === c.id;
                        const status = c.status;
                        const extraCount = Number(c.group_extra_count || 0);
                        return (
                          <button
                            key={c.id}
                            type="button"
                            className={`mm-attrCatItem ${active ? "active" : ""}`}
                            onClick={() => {
                              setAttrSelectedCategoryId(c.id);
                              if (useCatalogTreeForFeatures) applySelectedCatalogId(c.id);
                            }}
                          >
                            <span className={`mm-nodeDot ${status === "ok" ? "ok" : status === "warn" || status === "new" ? "warn" : "none"}`} />
                            <span className="mm-attrCatContent">
                              <span className="mm-attrCatTop">
                                <span className="mm-catPath">{c.name}</span>
                                {extraCount > 0 ? <span className="mm-attrCatBadge">+{extraCount}</span> : null}
                              </span>
                              <span className="mm-breadcrumbs">{c.path}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>

                <div className="mm-attrRight">
                  {!activeAttrCategoryId ? (
                    <div className="empty-state">Выберите категорию слева.</div>
                  ) : attrDetailsLoading ? (
                    <div className="muted">Загрузка характеристик...</div>
                  ) : attrDetailsError ? (
                    <div className="mm-emptyWorkspace">
                      <div className="mm-emptyTitle">
                        {attrDetailsError.includes("CATEGORY_NOT_MAPPED") ? "Для этой категории еще нет рабочей привязки" : "Не удалось загрузить параметры"}
                      </div>
                      <div className="mm-emptyText">
                        {attrDetailsError.includes("CATEGORY_NOT_MAPPED")
                          ? "Сначала задай общую привязку категории или перейди в конкретную дочернюю категорию, где привязка уже определена."
                          : attrDetailsError}
                      </div>
                    </div>
                  ) : !attrDetails ? (
                    <div className="muted">Нет данных по категории.</div>
                  ) : (
                    <>
                      {renderFeatureDetailExtra ? (
                        <div className="mm-tabs" style={{ marginBottom: 12 }}>
                          <button
                            type="button"
                            className={`mm-tab ${featureView === "marketplaces" ? "active" : ""}`}
                            onClick={() => onFeatureViewChange?.("marketplaces")}
                          >
                            Маркетплейсы
                          </button>
                          <button
                            type="button"
                            className={`mm-tab ${featureView === "competitors" ? "active" : ""}`}
                            onClick={() => onFeatureViewChange?.("competitors")}
                          >
                            Конкуренты
                          </button>
                        </div>
                      ) : null}

                      {renderFeatureDetailExtra && featureView === "competitors" && activeAttrCategoryId ? (
                        <div className="mm-featurePaneSingle">
                          {renderFeatureDetailExtra(
                            activeAttrCategoryId,
                            attrDetails?.category?.name || selectedCatalogNode?.name || ""
                          )}
                        </div>
                      ) : (
                        <>
                      <div className="mm-attrHeader">
                        <div className="mm-attrHeaderMain">
                          <div className="mm-catPath">{attrDetails.category.name}</div>
                          <div className="mm-breadcrumbs">{attrDetails.category.path}</div>
                        </div>
                        <div className="mm-attrHeaderMeta">
                          {mappingProvidersForUi.map((providerCode) => (
                            <div key={providerCode} className="mm-attrHeaderPill">
                              {PROVIDER_SLOTS[providerCode]}
                              <span>{Number(attrDetails.providers?.[providerCode]?.count || 0)}</span>
                            </div>
                          ))}
                          <div className="mm-attrHeaderPill">
                            Подтверждено
                            <span>
                              {Number(attrDetails.master_template?.confirmed_count || 0)} / {Number(attrDetails.master_template?.row_count || 0)}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="mm-attrMetaBar">
                        {mappingProvidersForUi.map((providerCode) => (
                          <div key={providerCode} className="mm-attrMetaItem mm-attrMetaItemWide">
                            <span>Категория {PROVIDER_SLOTS[providerCode]}</span>
                            <strong>
                              {attrDetails.providers?.[providerCode]?.category_id
                                ? attrDetails.providers?.[providerCode]?.category_name || attrDetails.providers?.[providerCode]?.category_id
                                : "Категория площадки не найдена"}
                            </strong>
                          </div>
                        ))}
                        <div className="mm-attrMetaItem">
                          <span>Основа</span>
                          <strong>{Number(attrDetails.master_template?.base_count || 0)}</strong>
                        </div>
                        <div className="mm-attrMetaItem">
                          <span>Категорийные</span>
                          <strong>{Number(attrDetails.master_template?.category_count || 0)}</strong>
                        </div>
                        {attrDetails.template_id ? (
                          <Link className="btn mm-metaLink" to={`/templates/${encodeURIComponent(activeAttrCategoryId)}`}>
                            Открыть шаблон
                          </Link>
                        ) : null}
                      </div>

                      <div className="mm-tabs" style={{ marginBottom: 12 }}>
                        <button
                          type="button"
                          className={`mm-tab ${attrTemplateTab === "all" ? "active" : ""}`}
                          onClick={() => setAttrTemplateTab("all")}
                        >
                          Все
                        </button>
                        <button
                          type="button"
                          className={`mm-tab ${attrTemplateTab === "base" ? "active" : ""}`}
                          onClick={() => setAttrTemplateTab("base")}
                        >
                          Основа товара
                          <span className="mm-tabCount">{attrBaseRowsCount}</span>
                        </button>
                        <button
                          type="button"
                          className={`mm-tab ${attrTemplateTab === "category" ? "active" : ""}`}
                          onClick={() => setAttrTemplateTab("category")}
                        >
                          Параметры категории
                          <span className="mm-tabCount">{attrCategoryRowsCount}</span>
                        </button>
                      </div>

                      {attrDraftAutoBuilt && !attrHasServerSaved ? (
                        <div className="mm-draftNotice">
                          <div className="mm-draftNoticeTitle">Черновик собран автоматически</div>
                          <div className="muted" style={{ lineHeight: 1.45 }}>
                            Для этой категории не было сохраненного маппинга. Система сначала использовала совпадения из уже сохраненных категорий, а недостающее добрала по структуре Я.Маркета. Проверь строки, при необходимости поправь и сохрани мастер-шаблон.
                          </div>
                        </div>
                      ) : null}

                      <div className="mm-attrEditorGrid">
                        <div className="mm-workbench mm-workbenchSidebar">
                          <div className="mm-workbenchHead mm-workbenchHeadCompact">
                            <div>
                              <div className="mm-workbenchTitle">Поля площадок</div>
                              <div className="mm-workbenchSub">
                                {mappingProvidersForUi
                                  .map((providerCode) => {
                                    const stats = providerParamStats[providerCode];
                                    return `${PROVIDER_SLOTS[providerCode]}: ${stats?.visible || 0} из ${stats?.total || 0}${stats?.hiddenUsed ? `, скрыто ${stats.hiddenUsed}` : ""}`;
                                  })
                                  .join(" · ")}
                              </div>
                            </div>
                          </div>

                          <div className="mm-attrParams">
                            {mappingProvidersForUi.map((providerCode) => (
                              <div key={providerCode} className="mm-attrParamCol">
                                <div className="mm-attrParamList">
                                  {(visibleProviderParamSections[providerCode] || []).map((section) => (
                                    <div key={`${providerCode}-${section.key}`} className="mm-attrParamSection">
                                      <div className="mm-attrParamSectionHead">
                                        <div className="mm-attrParamSectionTitle">{section.title}</div>
                                        <div className="mm-attrParamSectionSub">{section.subtitle}</div>
                                      </div>
                                      {section.items.length === 0 ? (
                                        <div className="muted mm-attrParamSectionEmpty">Нет доступных полей.</div>
                                      ) : (
                                        section.items.map((p) => (
                                          <button
                                            key={`${providerCode}-${p.id}`}
                                            type="button"
                                            className={`mm-attrParamItem ${dragParamKey === `${providerCode}:${String(p.id)}` ? "isDragging" : ""}`}
                                            draggable={attrEditMode}
                                            onDragStart={(e) => onDragParam(providerCode, p, e)}
                                            onDragEnd={onDragEndParam}
                                            disabled={!attrEditMode}
                                          >
                                            <span className="mm-attrParamTop">
                                              <span>{p.name}</span>
                                              <span className="mm-attrParamKind">{humanizeParamKind(p.kind)}</span>
                                            </span>
                                            <span className="mm-attrParamValues">{valuesText(p.values)}</span>
                                          </button>
                                        ))
                                      )}
                                    </div>
                                  ))}
                                  {(visibleProviderParams[providerCode] || []).length === 0 && (
                                    <div className="muted">Все параметры из пула уже использованы.</div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="mm-templateBoard">
                          <div className="mm-workbenchHead mm-workbenchHeadCompact">
                            <div>
                              <div className="mm-workbenchTitle">Строки PIM</div>
                              <div className="mm-workbenchSub">Сопоставляй поля площадок со строками PIM, подтверждай готовые строки и сохраняй шаблон категории.</div>
                            </div>
                          </div>

                        <div className="mm-attrToolbar">
                          <div className="mm-attrToolbarMain">
                            <input
                              className="pn-input mm-attrSearch"
                              placeholder="Поиск по строкам PIM и сопоставленным параметрам..."
                              value={attrRowQuery}
                              onChange={(e) => setAttrRowQuery(e.target.value)}
                            />
                            <div className="mm-attrFilterChips">
                              <button type="button" className={`mm-chipBtn ${attrRowFilter === "attention" ? "isActive" : ""}`} onClick={() => setAttrRowFilter("attention")}>
                                Требуют внимания
                                <span>{attrRowsStats.attention}</span>
                              </button>
                              <button type="button" className={`mm-chipBtn ${attrRowFilter === "unmapped" ? "isActive" : ""}`} onClick={() => setAttrRowFilter("unmapped")}>
                                Не сопоставлены
                                <span>{attrRowsStats.unmapped}</span>
                              </button>
                              <button type="button" className={`mm-chipBtn ${attrRowFilter === "ready" ? "isActive" : ""}`} onClick={() => setAttrRowFilter("ready")}>
                                Готово
                                <span>{attrRowsStats.ready}</span>
                              </button>
                              <button type="button" className={`mm-chipBtn ${attrRowFilter === "all" ? "isActive" : ""}`} onClick={() => setAttrRowFilter("all")}>
                                Все строки
                                <span>{attrRowsStats.total}</span>
                              </button>
                            </div>
                          </div>
                          <div className="mm-attrToolbarActions">
                            {!attrHasServerSaved ? (
                              <button className="btn" type="button" onClick={clearAttrDraft} disabled={!attrDraftExists || attrSaving || attrAiMatching}>
                                Очистить черновик
                              </button>
                            ) : (
                              <button className="btn" type="button" onClick={() => setAttrEditMode(true)} disabled={attrEditMode || attrSaving || attrAiMatching}>
                                Редактировать
                              </button>
                            )}
                            <button className="btn" type="button" onClick={addAttrRow} disabled={!attrEditMode || attrTemplateTab === "base"}>
                              Добавить строку
                            </button>
                            <button className="btn" type="button" onClick={runAiMatch} disabled={attrAiMatching || attrSaving || !attrEditMode}>
                              {attrAiMatching ? "Сопоставляю..." : "Сопоставить с AI"}
                            </button>
                            <button className="btn btn-primary" type="button" onClick={saveAttrRows} disabled={attrSaving || !attrEditMode}>
                              {attrSaving ? "Сохраняю..." : "Сохранить шаблон"}
                            </button>
                          </div>
                        </div>

                        <div className="mm-attrTableWrap">
                          <div className="mm-attrTable">
                          <div className="mm-attrTh">Каталог</div>
                          {mappingProvidersForUi.map((providerCode) => (
                            <div key={`th-${providerCode}`} className="mm-attrTh">{PROVIDER_SLOTS[providerCode]}</div>
                          ))}
                          <div className="mm-attrTh mm-attrThReady">
                            <label className="mm-check mm-checkHeader">
                              <input
                                type="checkbox"
                                checked={allRowsConfirmed}
                                onChange={(e) => setAllRowsConfirmed(e.target.checked)}
                                disabled={!attrEditMode || !attrRows.length}
                              />
                              <span className="mm-checkMark" />
                              <span>готово</span>
                            </label>
                          </div>

                          {groupedAttrRows.map((section) => (
                            <div key={`group-${section.group}`} className="mm-attrRow">
                              <div className="mm-attrGroupRow">
                                <span>{section.group}</span>
                                <span className="mm-attrGroupCount">{section.rows.length}</span>
                              </div>
                              {section.rows.map((row) => {
                                const serviceRow = isServiceRow(row, serviceParamDefs);
                                const rowGroupValue = normalizeParamGroup(row.group, row.catalog_name);
                                return (
                                  <div key={row.id} className="mm-attrRow">
                                    <div id={`attr-row-anchor-${row.id}`} className="mm-attrTd mm-attrTdCatalog">
                                      <div className="mm-attrCatalogLine">
                                        <input
                                          className="pn-input"
                                          placeholder="Название параметра каталога"
                                          value={row.catalog_name || ""}
                                          onChange={(e) => updateAttrRow(row.id, { catalog_name: e.target.value })}
                                          list="mm-catalog-attr-options"
                                          disabled={!attrEditMode}
                                        />
                                        <select
                                          className="pn-input mm-groupSelect"
                                          value={rowGroupValue}
                                          onChange={(e) => updateAttrRow(row.id, { group: e.target.value })}
                                          disabled={!attrEditMode}
                                        >
                                          {PARAM_GROUPS.map((g) => (
                                            <option key={g} value={g}>{g}</option>
                                          ))}
                                        </select>
                                      </div>
                                    </div>
                                    {mappingProvidersForUi.map((providerCode) => {
                                      const providerValue = row.provider_map?.[providerCode] || { id: "", name: "", kind: "", values: [], export: false };
                                      const dropKey = `${row.id}:${providerCode}`;
                                      return (
                                        <div
                                          key={dropKey}
                                          className={`mm-attrTd mm-dropCell mm-dropCellRich ${dropCellKey === dropKey ? "isDragOver" : ""}`}
                                          onDragOver={(e) => {
                                            if (dragProvider && dragProvider !== providerCode) {
                                              e.dataTransfer.dropEffect = "none";
                                              setDropCellKey((prev) => (prev === dropKey ? "" : prev));
                                              return;
                                            }
                                            if (!attrEditMode) {
                                              e.dataTransfer.dropEffect = "none";
                                              return;
                                            }
                                            e.preventDefault();
                                            e.dataTransfer.dropEffect = "copy";
                                            setDropCellKey(dropKey);
                                          }}
                                          onDragLeave={() => setDropCellKey((prev) => (prev === dropKey ? "" : prev))}
                                          onDrop={(e) => onDropParam(row.id, providerCode, e)}
                                        >
                                          {providerValue.name ? (
                                            <div className="mm-dropCellContent">
                                              <div className="mm-dropCellTop">
                                                <div className="mm-dropName">
                                                  <span>{providerValue.name}</span>
                                                  <span className="mm-attrParamKind">{humanizeParamKind(providerValue.kind)}</span>
                                                </div>
                                                <label className="mm-check">
                                                  <input type="checkbox" checked={!!providerValue.export} onChange={(e) => setAttrProviderValue(row.id, providerCode, { ...providerValue, export: e.target.checked })} disabled={!attrEditMode} />
                                                  <span className="mm-checkMark" />
                                                  <span>отправлять</span>
                                                </label>
                                              </div>
                                              <div className="mm-dropMeta">
                                                <span className="mm-attrParamValues">{valuesText(providerValue.values)}</span>
                                                <button className="btn mm-miniBtn" type="button" onClick={() => clearAttrProviderValue(row.id, providerCode)} disabled={!attrEditMode}>Очистить</button>
                                              </div>
                                            </div>
                                          ) : <span className="muted">Перетащите параметр</span>}
                                        </div>
                                      );
                                    })}
                                    <div className="mm-attrTd">
                                      <div className="mm-attrActionsCol">
                                        <label className="mm-check">
                                          <input type="checkbox" checked={!!row.confirmed} onChange={(e) => updateAttrRow(row.id, { confirmed: e.target.checked })} disabled={!attrEditMode} />
                                          <span className="mm-checkMark" />
                                          <span>готово</span>
                                        </label>
                                        <button className="btn mm-miniBtn" type="button" onClick={() => removeAttrRow(row.id)} disabled={serviceRow || !attrEditMode}>
                                          Удалить
                                        </button>
                                      </div>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ))}

                          {groupedAttrRows.length === 0 && (
                            <div className="mm-attrEmpty">
                              {attrRowsStats.total
                                ? "По текущему фильтру строки не найдены."
                                : "Пока нет строк. Добавьте строку и сопоставьте параметры площадок."}
                            </div>
                          )}
                        </div>
                      </div>
                        </div>
                      </div>
                      <datalist id="mm-catalog-attr-options">
                        {catalogNameSuggests.map((name) => (
                          <option key={name} value={name} />
                        ))}
                      </datalist>
                        </>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="card mm-card">
          <div className="mm-title" style={{ marginBottom: 8 }}>Экспорт</div>
          <div className="muted">Следующий шаг: подготовка и публикация контента по сопоставленным категориям и параметрам.</div>
        </div>
      )}

      {modalOpen && (
        <div className="pg-modalBackdrop" onClick={() => setModalOpen(false)}>
          <div className="pg-modal pg-modalWide" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">
                  Выбор категории площадки - {displayProviders.find((x) => x.code === modalProvider)?.title || modalProvider}
                </div>
              </div>
              <button className="btn" type="button" onClick={() => setModalOpen(false)}>Закрыть</button>
            </div>

            <div className="pg-modalBody">
              {!!modalCatalogPath && (
                <div className="pg-addActions" style={{ marginBottom: 10 }}>
                  <div>
                    <div className="muted">
                      Категория каталога: {splitPath(modalCatalogPath).crumbs || "Корень"}
                    </div>
                    <div style={{ fontWeight: 700 }}>{splitPath(modalCatalogPath).node}</div>
                  </div>
                </div>
              )}

              <input className="pn-input" placeholder="Поиск по категориям площадки..." value={modalQuery} onChange={(e) => setModalQuery(e.target.value)} />

              {modalProvider && !(providerCategories[modalProvider] || []).length ? (
                <div className="mm-emptyMap" style={{ marginTop: 10 }}>
                  <div className="mm-emptyTitle">Дерево категорий площадки не загружено</div>
                  <div className="muted">Для этого провайдера пока нет локального справочника категорий. Существующие связи сохраняются, но выбрать новую категорию сейчас нельзя.</div>
                </div>
              ) : null}

              <div className="pg-addActions" style={{ marginTop: 10 }}>
                <div className="muted">Найдено: {modalItems.length}</div>
              </div>
              <div className="muted" style={{ marginTop: 8 }}>
                Связь, заданная на категории, наследуется вниз. Если у дочерних категорий уже есть собственные привязки, сначала очистите их отдельной операцией из правого блока.
              </div>

              <div className="pg-addList" style={{ maxHeight: "55vh", marginTop: 10 }}>
                <button
                  type="button"
                  className={`pg-itemRow pg-itemRowSelectable ${!modalSelectedProviderCategoryId ? "active" : ""}`}
                  style={{ width: "100%", textAlign: "left" }}
                  onClick={() => setModalSelectedProviderCategoryId("")}
                  disabled={saving}
                >
                  <div>
                    <div style={{ fontWeight: 700 }}>Не сопоставлять</div>
                  </div>
                </button>
                {modalItemsOrdered.map((it) => (
                  <button
                    key={it.id}
                    type="button"
                    className={`pg-itemRow pg-itemRowSelectable ${modalSelectedProviderCategoryId === it.id ? "active" : ""}`}
                    style={{ width: "100%", textAlign: "left" }}
                    onClick={() => setModalSelectedProviderCategoryId(it.id)}
                    disabled={saving}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>{splitPath(it.path || it.name).node}</div>
                      {splitPath(it.path || it.name).crumbs ? <div className="mm-breadcrumbs">{splitPath(it.path || it.name).crumbs}</div> : null}
                    </div>
                  </button>
                ))}
                {!modalItems.length && <div className="muted">Ничего не найдено.</div>}
              </div>

              <div className="pg-modalActions mm-modalActionsRow">
                <button className="btn mm-modalBtn mm-modalBtnPrimary" type="button" onClick={saveModalSelection} disabled={saving}>
                  Сохранить
                </button>
                <button className="btn mm-modalBtn mm-modalBtnSecondary" type="button" onClick={() => setModalOpen(false)} disabled={saving}>
                  Отмена
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {clearModalOpen && (
        <div className="pg-modalBackdrop" onClick={() => setClearModalOpen(false)}>
          <div className="pg-modal" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">Очистить дочерние привязки</div>
                <div className="muted" style={{ marginTop: 4 }}>
                  Все прямые привязки дочерних категорий для {PROVIDER_SLOTS[clearModalProvider] || clearModalProvider} будут удалены.
                </div>
              </div>
              <button className="btn" type="button" onClick={() => setClearModalOpen(false)} disabled={saving}>Закрыть</button>
            </div>

            <div className="pg-modalBody">
              <div className="mm-emptyMap" style={{ marginTop: 0 }}>
                <div className="mm-emptyTitle">Внимание</div>
                <div className="muted">
                  После очистки можно будет задать одну общую привязку на выбранной родительской категории. Дочерние категории потеряют собственные связи для этой площадки.
                </div>
              </div>

              <label className="mm-check" style={{ marginTop: 14 }}>
                <input
                  type="checkbox"
                  checked={clearModalPreserveTemplates}
                  onChange={(e) => setClearModalPreserveTemplates(e.target.checked)}
                />
                <span className="mm-checkMark" />
                <span>Сохранить мастер-шаблоны отвязанных категорий</span>
              </label>

              <div className="mm-breadcrumbs" style={{ marginTop: 10 }}>
                Чекбокс включен по умолчанию. Система сохранит шаблоны отвязанных категорий и их можно будет использовать дальше.
              </div>
            </div>

            <div className="pg-modalActions">
              <button className="btn mm-modalBtn mm-modalBtnSecondary" type="button" onClick={() => setClearModalOpen(false)} disabled={saving}>
                Отмена
              </button>
              <button className="btn mm-modalBtn mm-modalBtnDanger" type="button" onClick={() => void clearDescendantBindingsAndContinue()} disabled={saving}>
                {saving ? "Очищаю..." : "Очистить и продолжить"}
              </button>
            </div>
          </div>
        </div>
      )}

      {savedToast && (
        <div className="mm-savedToast">
          <span>{savedToastText}</span>
          {savedTemplateId ? (
            <Link to={`/templates/${encodeURIComponent(activeAttrCategoryId || "")}`}>Открыть шаблон</Link>
          ) : null}
        </div>
      )}

    </div>
  );
}
