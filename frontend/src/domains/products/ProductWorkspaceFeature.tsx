import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Alert from "../../components/ui/Alert";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Card from "../../components/ui/Card";
import EmptyState from "../../components/ui/EmptyState";
import InspectorPanel from "../../components/data/InspectorPanel";
import WorkspaceFrame from "../../components/layout/WorkspaceFrame";
import { api } from "../../lib/api";
import { toRenderableMediaUrl } from "../../lib/media";
import ProductCompetitorPanel from "./ProductCompetitorPanel";

type ProductFeatureValue = {
  code?: string;
  name?: string;
  value?: string;
  values?: string[];
  required?: boolean;
  param_group?: string;
  field_layer?: string;
  fill_source?: string;
  locked?: boolean;
  source_values?: Record<string, unknown>;
};

type FeatureValueUpdate = {
  feature: ProductFeatureValue;
  value: string;
};

type ProductRelation = {
  id?: string;
  sku?: string;
  sku_gt?: string;
  name?: string;
};

type ProductMedia = {
  url: string;
  caption?: string;
  source?: string;
  source_type?: string;
  status?: string;
  needs_review?: boolean;
  selected?: boolean;
  order?: number;
  export_order?: number;
};

type ProductContent = {
  description?: string;
  features?: ProductFeatureValue[];
  source_values?: Record<string, unknown>;
  media?: ProductMedia[];
  media_images?: ProductMedia[];
  media_videos?: ProductMedia[];
  media_cover?: ProductMedia[];
  documents?: { name?: string; url?: string }[];
  analogs?: ProductRelation[];
  related?: ProductRelation[];
};

type ProductData = {
  id: string;
  title: string;
  sku_pim?: string;
  sku_gt?: string;
  status?: string;
  category_id?: string;
  group_id?: string;
  content?: ProductContent;
};

type VariantData = {
  id: string;
  title?: string;
  sku_pim?: string;
  sku_gt?: string;
  status?: string;
  content?: ProductContent;
};

type ProductInfoModel = {
  has_template?: boolean;
  template_id?: string;
  template_name?: string;
  status?: string;
  attributes_count?: number;
  attributes?: ProductFeatureValue[];
};

type ProductResponse = {
  product: ProductData;
  variants?: VariantData[];
  info_model?: ProductInfoModel;
};

type ProductWorkspaceSummaryResp = {
  items?: Array<{
    id: string;
    title?: string;
    name?: string;
    category_id?: string;
    sku_pim?: string;
    sku_gt?: string;
    group_id?: string;
    preview_url?: string;
    content?: ProductContent;
  }>;
};

type CompetitorSourceSummary = {
  source_id?: string;
  status?: string;
  label?: string;
  confirmed_count?: number;
  actionable_count?: number;
  last_scanned_at?: string;
};

type ProductCompetitorContextResp = {
  counts?: {
    needs_review?: number;
    confirmed_links?: number;
  };
  source_summaries?: CompetitorSourceSummary[];
};

type CompetitorDiscoveryRunResp = {
  run?: {
    id?: string;
    status?: string;
    scanned_products_count?: number;
    created_count?: number;
    updated_count?: number;
  };
};

type CompetitorSafeConfirmResp = {
  ok?: boolean;
  confirmed_count?: number;
  skipped?: Array<{ reason?: string }>;
};

type CompetitorEnrichBatchResp = {
  ok?: boolean;
  queued_count?: number;
  skipped?: Array<{ reason?: string }>;
};

type CompetitorSkuStatus = {
  label: string;
  detail: string;
  tone: "active" | "pending" | "danger" | "neutral";
  sources?: Array<{
    id: string;
    label: string;
    tone: "active" | "pending" | "danger" | "neutral";
  }>;
};

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
};

type MarketplaceChannel = {
  title: string;
  status: string;
  content_rating: string;
  stores_count?: number;
  stores?: Array<{ store_id: string; store_title: string; business_id?: string; status: string; content_rating?: number | string }>;
};

type ExternalSystemChannel = {
  title: string;
  status: string;
};

type CompetitorChannel = {
  key: string;
  title: string;
  status: string;
  url: string;
};

type ChannelsSummary = {
  marketplaces: MarketplaceChannel[];
  external_systems: ExternalSystemChannel[];
  competitors: CompetitorChannel[];
};

type ProductParameterFlowMarketplace = {
  provider: string;
  provider_label: string;
  target_id?: string;
  target_name?: string;
  output_value?: string;
  status?: string;
  label?: string;
  mapping_reason?: string;
};

type ProductParameterFlowBlocker = {
  code?: string;
  parameter?: string;
  target?: string;
  provider?: string;
  target_id?: string;
  message?: string;
};

type ProductParameterFlowRow = {
  key: string;
  code?: string;
  name: string;
  value?: string;
  status?: string;
  marketplaces?: ProductParameterFlowMarketplace[];
};

type ProductParameterFlow = {
  summary?: {
    features_ready?: number;
    features_attention?: number;
    features_empty?: number;
    source_values?: number;
    blockers?: number;
  };
  blockers?: ProductParameterFlowBlocker[];
  items?: ProductParameterFlowRow[];
};

type SectionId =
  | "overview"
  | "attributes"
  | "media"
  | "sources"
  | "channels"
  | "competitors"
  | "validation"
  | "relations"
  | "analogs"
  | "accessories"
  | "variants"
  | "create-flow";

const SECTION_LABELS: Array<{ id: SectionId; label: string; meta: string }> = [
  { id: "overview", label: "Описание", meta: "контекст SKU" },
  { id: "attributes", label: "Параметры", meta: "значения и источники" },
  { id: "sources", label: "Источники", meta: "импорт, excel, конкуренты" },
  { id: "channels", label: "Площадки", meta: "вывод и альтернативы" },
  { id: "competitors", label: "Источники", meta: "поиск и насыщение" },
  { id: "media", label: "Медиа", meta: "S3 assets" },
  { id: "validation", label: "Валидация", meta: "ошибки перед экспортом" },
  { id: "relations", label: "Связи", meta: "аналоги и комплекты" },
  { id: "variants", label: "Варианты", meta: "SKU family" },
  { id: "create-flow", label: "Создание", meta: "новый процесс" },
];

const SECTION_IDS = new Set<SectionId>(SECTION_LABELS.map((section) => section.id));
const PRODUCT_CONTEXT_CACHE_KEY = "smartpim_last_product_context_v1";

const PRODUCT_NAV_ITEMS: Array<{ id: SectionId; label: string; meta: string }> = [
  { id: "overview", label: "Описание", meta: "контекст SKU" },
  { id: "attributes", label: "Параметры", meta: "значения и источники" },
  { id: "competitors", label: "Источники", meta: "площадки и конкуренты" },
  { id: "media", label: "Медиа", meta: "выбор и порядок" },
  { id: "validation", label: "Проверка", meta: "блокеры экспорта" },
  { id: "relations", label: "Связи", meta: "family, аналоги, комплекты" },
];

function sectionFromTab(value: string | null): SectionId {
  const tab = normalizeText(value).toLowerCase();
  if (tab === "params" || tab === "features" || tab === "parameters") return "attributes";
  if (tab === "description") return "overview";
  if (tab === "platforms" || tab === "marketplaces") return "channels";
  if (tab === "sources" || tab === "competitor" || tab === "competitors" || tab === "competitor_links" || tab === "links") return "competitors";
  if (SECTION_IDS.has(tab as SectionId)) return tab as SectionId;
  return "overview";
}

function normalizeText(value: unknown): string {
  return String(value ?? "").trim();
}

function productExportHref(productId: string) {
  return `/catalog/exchange?tab=export&product=${encodeURIComponent(productId)}`;
}

type ProductNextAction = {
  title: string;
  detail: string;
  cta: string;
  href?: string;
  tab?: SectionId;
  tone: "active" | "pending" | "danger" | "neutral";
};

function hasActiveCompetitorLink(channels: ChannelsSummary | null): boolean {
  return Boolean((channels?.competitors || []).some((item) => toneForStatus(item.status) === "active"));
}

function buildProductNextAction({
  product,
  infoModel,
  features,
  media,
  channels,
}: {
  product: ProductData;
  infoModel: ProductInfoModel | null;
  features: ProductFeatureValue[];
  media: ProductMedia[];
  channels: ChannelsSummary | null;
}): ProductNextAction {
  const categoryId = normalizeText(product.category_id);
  const hasInfoModel = Boolean(infoModel?.has_template || infoModel?.template_id || infoModel?.attributes_count || features.length);
  const description = normalizeText(product.content?.description);
  const competitorReady = hasActiveCompetitorLink(channels);

  if (!description) {
    return {
      title: "Найти описание из источника",
      detail: "Описание пустое. Проверьте подтвержденные карточки конкурентов или импорт площадки.",
      cta: "Открыть источники",
      tab: "competitors",
      tone: "pending",
    };
  }

  if (!media.length) {
    return {
      title: competitorReady ? "Проверить медиа" : "Подтвердить источник медиа",
      detail: competitorReady
        ? "Ссылки конкурентов есть, но в карточке нет изображений для экспорта."
        : "Сначала подтвердите точную карточку конкурента или импортируйте фото с площадки.",
      cta: competitorReady ? "Открыть медиа" : "Открыть источники",
      tab: competitorReady ? "media" : "competitors",
      tone: "danger",
    };
  }

  const requiredMissing = features.filter((feature) => feature.required && !featureValue(feature)).length;
  if (requiredMissing > 0) {
    return {
      title: "Заполнить обязательные параметры",
      detail: `${requiredMissing} обязательных полей еще пустые.`,
      cta: "Открыть валидацию",
      tab: "validation",
      tone: "danger",
    };
  }

  if (!hasInfoModel && !features.length) {
    return {
      title: "Проверить экспорт SKU",
      detail: "Описание и медиа есть. Readiness batch покажет, каких параметров или значений не хватает для площадок.",
      cta: "Открыть экспорт",
      href: productExportHref(product.id),
      tone: "active",
    };
  }

  return {
    title: "Проверить экспорт SKU",
    detail: "Описание, медиа и базовые параметры есть. Запустите readiness batch по безопасным магазинам.",
    cta: "Открыть экспорт",
    href: productExportHref(product.id),
    tone: "active",
  };
}

function featureIdentity(value: unknown): string {
  return normalizeText(value).toLowerCase().replace(/[\s-]+/g, "_");
}

function parameterLookupText(value: unknown): string {
  return normalizeText(value)
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function parameterAliasCandidates(value: unknown): string[] {
  const text = parameterLookupText(value);
  const aliases = new Set<string>([text]);
  const withoutSlash = text.replace(/\s+товара\b/g, "").replace(/\s+устройства\b/g, "").trim();
  if (withoutSlash) aliases.add(withoutSlash);
  if (text.includes("упаков") && text.includes("вес")) aliases.add("вес упаковки");
  if (text.includes("упаков") && text.includes("длин")) aliases.add("длина упаковки");
  if (text.includes("упаков") && text.includes("шир")) aliases.add("ширина упаковки");
  if (text.includes("упаков") && text.includes("выс")) aliases.add("высота упаковки");
  if (!text.includes("упаков") && text.includes("вес")) aliases.add("вес устройства");
  if (!text.includes("упаков") && text.includes("длин")) aliases.add("длина устройства");
  if (!text.includes("упаков") && text.includes("шир")) aliases.add("ширина устройства");
  if (!text.includes("упаков") && text.includes("выс")) aliases.add("высота устройства");
  return Array.from(aliases).filter(Boolean);
}

function featureSearchHaystack(feature: ProductFeatureValue): string[] {
  return [feature.name, feature.code]
    .map(parameterLookupText)
    .filter(Boolean);
}

function findFeatureByParameter(features: ProductFeatureValue[], parameter: unknown): ProductFeatureValue | null {
  const candidates = parameterAliasCandidates(parameter);
  if (!candidates.length) return null;

  const exact = features.find((feature) => {
    const haystack = featureSearchHaystack(feature);
    return candidates.some((candidate) => haystack.includes(candidate));
  });
  if (exact) return exact;

  const contains = features.find((feature) => {
    const haystack = featureSearchHaystack(feature);
    return candidates.some((candidate) => haystack.some((item) => item.includes(candidate) || candidate.includes(item)));
  });
  return contains || null;
}

const OZON_PACKAGE_DIMENSION_FIELDS: Array<{ key: string; label: string; parameter: string; placeholder: string }> = [
  { key: "length", label: "Длина, мм", parameter: "Длина упаковки/товара", placeholder: "например 170" },
  { key: "width", label: "Ширина, мм", parameter: "Ширина упаковки/товара", placeholder: "например 90" },
  { key: "height", label: "Высота, мм", parameter: "Высота упаковки/товара", placeholder: "например 40" },
  { key: "weight", label: "Вес, г", parameter: "Вес упаковки/товара", placeholder: "например 320" },
];

function isProductFeatureCode(codeOrName: unknown): boolean {
  const raw = featureIdentity(codeOrName);
  if (!raw) return true;
  if (raw.startsWith("описание") || raw.startsWith("description")) return false;
  return !new Set([
    "description",
    "описание",
    "product_description",
    "media",
    "media_images",
    "media_cover",
    "images",
    "photos",
    "title",
    "name",
  ]).has(raw);
}

function buildCategoryPath(nodes: CatalogNode[], categoryId?: string): string {
  const target = normalizeText(categoryId);
  if (!target) return "";
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const chain: string[] = [];
  const seen = new Set<string>();
  let current = byId.get(target);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    chain.push(current.name);
    current = current.parent_id ? byId.get(current.parent_id) ?? null : null;
  }
  return chain.reverse().join(" / ");
}

function flattenMedia(content?: ProductContent): ProductMedia[] {
  if (!content) return [];
  const sets = [content.media_cover, content.media_images, content.media];
  const out: ProductMedia[] = [];
  const seen = new Set<string>();
  for (const group of sets) {
    for (const item of group || []) {
      const url = normalizeText(item?.url);
      if (!url || seen.has(url)) continue;
      seen.add(url);
      out.push({
        ...item,
        url,
        caption: normalizeText(item?.caption) || undefined,
      });
    }
  }
  return out;
}

function isMediaWaitingForReview(item: ProductMedia): boolean {
  return normalizeText(item.status).toLowerCase() === "needs_review"
    || item.needs_review === true
    || normalizeText(item.source_type).toLowerCase() === "external_hotlink";
}

function featureValue(feature: ProductFeatureValue): string {
  const value = normalizeText(feature.value);
  if (value) return value;
  const values = Array.isArray(feature.values) ? feature.values.map((item) => normalizeText(item)).filter(Boolean) : [];
  return values.join(", ");
}

function compactText(value: string, max = 96): string {
  const normalized = normalizeText(value).replace(/\s+/g, " ");
  if (normalized.length <= max) return normalized;
  return `${normalized.slice(0, max - 1).trim()}…`;
}

function featureKey(feature: ProductFeatureValue, index: number): string {
  return normalizeText(feature.code) || normalizeText(feature.name) || `feature-${index}`;
}

function featureLabel(feature: ProductFeatureValue): string {
  return normalizeText(feature.name) || normalizeText(feature.code) || "Параметр";
}

function featureGroup(feature: ProductFeatureValue): string {
  return normalizeText(feature.param_group) || "Без группы";
}

function sourceEntriesForFeature(feature: ProductFeatureValue) {
  const entries: Array<{ provider: string; store: string; raw: string; resolved: string; canonical: string }> = [];
  const sourceValues = feature.source_values && typeof feature.source_values === "object" ? feature.source_values : {};
  for (const provider of Object.keys(sourceValues)) {
    const providerValue = sourceValues[provider];

    if (typeof providerValue === "string" || typeof providerValue === "number" || typeof providerValue === "boolean") {
      const value = normalizeText(providerValue);
      entries.push({
        provider,
        store: "value",
        raw: value,
        resolved: value,
        canonical: normalizeText(feature.value) || value,
      });
      continue;
    }

    if (Array.isArray(providerValue)) {
      providerValue.forEach((item, index) => {
        if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
          const value = normalizeText(item);
          entries.push({ provider, store: String(index + 1), raw: value, resolved: value, canonical: normalizeText(feature.value) || value });
          return;
        }
        if (!item || typeof item !== "object") return;
        const row = item as { source?: string; store?: string; resolved_value?: string; canonical_value?: string; raw_value?: string; value?: string };
        entries.push({
          provider,
          store: normalizeText(row.store) || normalizeText(row.source) || String(index + 1),
          raw: normalizeText(row.raw_value) || normalizeText(row.value),
          resolved: normalizeText(row.resolved_value) || normalizeText(row.value),
          canonical: normalizeText(row.canonical_value) || normalizeText(feature.value),
        });
      });
      continue;
    }

    if (!providerValue || typeof providerValue !== "object") continue;
    const stores = providerValue as Record<string, unknown>;
    const looksLikeSingleEvidence = "raw_value" in stores || "resolved_value" in stores || "canonical_value" in stores || "value" in stores;
    if (looksLikeSingleEvidence) {
      const item = stores as { resolved_value?: string; canonical_value?: string; raw_value?: string; value?: string };
      entries.push({
        provider,
        store: "value",
        raw: normalizeText(item.raw_value) || normalizeText(item.value),
        resolved: normalizeText(item.resolved_value) || normalizeText(item.value),
        canonical: normalizeText(item.canonical_value) || normalizeText(feature.value),
      });
      continue;
    }

    for (const store of Object.keys(stores)) {
      const item = stores[store];
      if (typeof item === "string" || typeof item === "number" || typeof item === "boolean") {
        const value = normalizeText(item);
        entries.push({ provider, store, raw: value, resolved: value, canonical: normalizeText(feature.value) || value });
        continue;
      }
      if (!item || typeof item !== "object") continue;
      const evidence = item as { resolved_value?: string; canonical_value?: string; raw_value?: string; value?: string };
      entries.push({
        provider,
        store,
        raw: normalizeText(evidence.raw_value) || normalizeText(evidence.value),
        resolved: normalizeText(evidence.resolved_value) || normalizeText(evidence.value),
        canonical: normalizeText(evidence.canonical_value) || normalizeText(feature.value),
      });
    }
  }
  return entries;
}

function isMarketplaceSource(provider: string) {
  const value = normalizeText(provider).toLowerCase();
  return value === "yandex_market" || value === "ozon";
}

function hasSourceEntryValue(entry: { raw: string; resolved: string; canonical: string }) {
  return Boolean(normalizeText(entry.raw) || normalizeText(entry.resolved) || normalizeText(entry.canonical));
}

function descriptionSourceEntries(content?: ProductContent) {
  const sourceValues = content?.source_values && typeof content.source_values === "object" ? content.source_values : {};
  const descriptions = sourceValues.descriptions && typeof sourceValues.descriptions === "object"
    ? sourceValues.descriptions as Record<string, unknown>
    : {};
  return Object.entries(descriptions)
    .map(([provider, raw]) => {
      if (typeof raw === "string" || typeof raw === "number" || typeof raw === "boolean") {
        const value = normalizeText(raw);
        return {
          provider,
          label: provider,
          detail: "value",
          value,
          updatedAt: "",
        };
      }
      if (!raw || typeof raw !== "object") return null;
      const item = raw as {
        site?: string;
        url?: string;
        store_id?: string;
        store_title?: string;
        source_product_id?: string;
        value?: string;
        count?: number;
        updated_at?: string;
      };
      const label = normalizeText(item.store_title) || normalizeText(item.site) || provider;
      const detail = normalizeText(item.url) || normalizeText(item.source_product_id) || normalizeText(item.store_id) || "source";
      return {
        provider,
        label,
        detail,
        value: normalizeText(item.value),
        updatedAt: normalizeText(item.updated_at),
      };
    })
    .filter((item): item is { provider: string; label: string; detail: string; value: string; updatedAt: string } => Boolean(item))
    .sort((left, right) => left.provider.localeCompare(right.provider, "ru"));
}

function packageFieldEvidence(targets: Array<{ key: string; label: string; feature: ProductFeatureValue }>) {
  const rows = targets.map((target) => {
    const value = featureValue(target.feature);
    const marketplaceEntries = sourceEntriesForFeature(target.feature).filter((entry) => isMarketplaceSource(entry.provider) && hasSourceEntryValue(entry));
    return {
      ...target,
      value,
      marketplaceEntries,
      hasMarketplaceEvidence: marketplaceEntries.length > 0,
    };
  });
  return {
    rows,
    filled: rows.filter((row) => row.value).length,
    fromMarketplace: rows.filter((row) => row.hasMarketplaceEvidence).length,
    missing: rows.filter((row) => !row.value).length,
  };
}

function siblingPackageSuggestion(
  variants: VariantData[],
  targets: Array<{ key: string; label: string; parameter: string; feature: ProductFeatureValue }>,
) {
  const suggestions = variants
    .map((variant) => {
      const variantFeatures = Array.isArray(variant.content?.features) ? variant.content?.features || [] : [];
      const updates = targets
        .map((target) => {
          if (featureValue(target.feature)) return null;
          const siblingFeature = findFeatureByParameter(variantFeatures, target.parameter);
          const value = siblingFeature ? featureValue(siblingFeature) : "";
          if (!value) return null;
          return { feature: target.feature, value, label: target.label };
        })
        .filter((item): item is { feature: ProductFeatureValue; value: string; label: string } => Boolean(item));
      return { variant, updates };
    })
    .filter((item) => item.updates.length);
  suggestions.sort((left, right) => {
    if (right.updates.length !== left.updates.length) return right.updates.length - left.updates.length;
    return normalizeText(left.variant.sku_gt || left.variant.sku_pim || left.variant.title).localeCompare(
      normalizeText(right.variant.sku_gt || right.variant.sku_pim || right.variant.title),
      "ru",
    );
  });
  return suggestions[0] || null;
}

function flowRowForFeature(parameterFlow: ProductParameterFlow | null, feature: ProductFeatureValue | null) {
  if (!feature) return null;
  const code = featureIdentity(feature.code);
  const name = featureIdentity(feature.name);
  return (parameterFlow?.items || []).find((row) => {
    const rowCode = featureIdentity(row.code);
    const rowName = featureIdentity(row.name);
    return (code && rowCode === code) || (name && rowName === name) || (code && rowName === code) || (name && rowCode === name);
  }) || null;
}

function productSourceFixHref(blocker: ProductParameterFlowBlocker, categoryId: string, productId: string) {
  const category = encodeURIComponent(normalizeText(categoryId));
  const product = encodeURIComponent(normalizeText(productId));
  const parameter = encodeURIComponent(normalizeText(blocker.parameter));
  const provider = encodeURIComponent(normalizeText(blocker.provider));
  const base = blocker.target === "values" ? "values" : "params";
  const query = new URLSearchParams();
  query.set("tab", base);
  if (category) query.set("category", normalizeText(categoryId));
  if (product) query.set("product", normalizeText(productId));
  if (parameter) query.set("parameter", normalizeText(blocker.parameter));
  if (provider) query.set("provider", normalizeText(blocker.provider));
  return `/sources?${query.toString()}`;
}

function productBlockerActionLabel(blocker: ProductParameterFlowBlocker) {
  if (blocker.code === "empty_value") return "Заполнить";
  if (blocker.code === "value_mapping_required") return "Сопоставить значение";
  if (blocker.code === "parameter_mapping_required") return "Сопоставить поле";
  return "Открыть";
}

function productBlockerTitle(blocker: ProductParameterFlowBlocker) {
  if (blocker.code === "empty_value") return "Пустое значение";
  if (blocker.code === "value_mapping_required") return "Нет значения для площадки";
  if (blocker.code === "parameter_mapping_required") return "Нет поля площадки";
  return "Блокер параметра";
}

function mediaSourceLabel(url: string): string {
  const normalized = normalizeText(url).toLowerCase();
  if (normalized.includes("/competitors/restore/")) return "re-store";
  if (normalized.includes("/competitors/store77/")) return "store77";
  if (normalized.includes("/uploads/")) return "S3";
  return "Медиа";
}

function mediaSourceTitle(item: ProductMedia): string {
  const source = normalizeText(item.source);
  if (source === "restore") return "re-store";
  if (source === "store77") return "store77";
  if (source === "ozon") return "Ozon";
  if (source === "yandex_market") return "Я.Маркет";
  return mediaSourceLabel(item.url);
}

function mediaShortName(url: string): string {
  const normalized = normalizeText(url);
  const parts = normalized.split(/[/?#]/).filter(Boolean);
  return compactText(parts[parts.length - 1] || normalized, 34);
}

function productSourceLabel(value: unknown): string {
  const raw = normalizeText(value);
  if (!raw) return "PIM";
  const normalized = raw.toLowerCase();
  if (normalized.includes("yandex") || normalized.includes("market")) return "Я.Маркет";
  if (normalized.includes("ozon")) return "Ozon";
  if (normalized.includes("restore")) return "re-store";
  if (normalized.includes("store77")) return "store77";
  if (normalized.includes("competitor")) return "Конкуренты";
  if (normalized.includes("upload") || normalized.includes("s3")) return "S3";
  return raw.length > 18 ? `${raw.slice(0, 18)}…` : raw;
}

function buildProductLineageSummary({
  features,
  media,
  channels,
}: {
  features: ProductFeatureValue[];
  media: ProductMedia[];
  channels: ChannelsSummary | null;
}) {
  const sourceLabels = new Set<string>();
  let sourceRows = 0;
  for (const feature of features) {
    const entries = sourceEntriesForFeature(feature);
    if (entries.length) sourceRows += 1;
    entries.forEach((entry) => {
      sourceLabels.add(productSourceLabel(entry.provider));
      if (entry.store && entry.store !== "value") sourceLabels.add(productSourceLabel(entry.store));
    });
  }
  const mediaSources = new Map<string, number>();
  media.forEach((item) => {
    const label = mediaSourceTitle(item);
    mediaSources.set(label, (mediaSources.get(label) || 0) + 1);
  });
  const activeMarketplaces = (channels?.marketplaces || []).filter((channel) => toneForStatus(channel.status) === "active").length;
  const exportMedia = media.filter((item) => item.selected !== false).length;
  return {
    filledFeatures: features.filter((feature) => featureValue(feature)).length,
    totalFeatures: features.length,
    sourceRows,
    sourceLabels: Array.from(sourceLabels).slice(0, 4),
    mediaTotal: media.length,
    exportMedia,
    mediaSources: Array.from(mediaSources.entries()).slice(0, 4),
    activeMarketplaces,
    marketplacesTotal: channels?.marketplaces?.length || 0,
  };
}

function inferBrand(title: string, features: ProductFeatureValue[] = []): string {
  const explicit = features.find((feature) => {
    const code = normalizeText(feature.code).toLowerCase();
    const name = normalizeText(feature.name).toLowerCase();
    return code === "brand" || name === "бренд";
  });
  const explicitValue = explicit ? featureValue(explicit) : "";
  if (explicitValue) return explicitValue;

  const value = normalizeText(title);
  const knownBrands = ["Apple", "Samsung", "Google", "Huawei", "Sony", "Dyson", "Nintendo", "Microsoft", "Meta", "Oculus", "Oura", "Яндекс"];
  return knownBrands.find((brand) => value.toLowerCase().includes(brand.toLowerCase())) || "Бренд не задан";
}

function qualityTone(ready: boolean): "active" | "pending" | "danger" | "neutral" {
  return ready ? "active" : "pending";
}

function fieldLayerLabel(value?: string) {
  const layer = normalizeText(value) || "features";
  if (layer === "content") return "Контент";
  if (layer === "documents") return "Документы";
  if (layer === "rich_content") return "Rich-content";
  if (layer === "system") return "Системное";
  if (layer === "media") return "Медиа";
  return "Характеристика";
}

function isReadonlySystemFeature(feature: ProductFeatureValue | null | undefined) {
  if (!feature) return false;
  const declaredSystem = Boolean(feature.locked || normalizeText(feature.field_layer) === "system" || normalizeText(feature.fill_source) === "system");
  if (!declaredSystem) return false;
  const key = `${normalizeText(feature.code)} ${normalizeText(feature.name)}`.toLowerCase();
  return [
    "sku_gt",
    "sku_pim",
    "sku pim",
    "sku gt",
    "наименование",
    "название товара",
    "title",
    "offer_id",
    "seller_code",
    "код продавца",
    "артикул продавца",
  ].some((token) => key.includes(token));
}

function featureFillSourceLabel(feature: ProductFeatureValue) {
  const fillSource = normalizeText(feature.fill_source);
  if (isReadonlySystemFeature(feature)) return "Заполнено системой";
  if (fillSource === "system" || feature.locked) return "Заполняет контент-менеджер";
  if (fillSource === "product_documents") return "Берется из документов товара";
  if (fillSource === "rich_content_editor") return "Берется из rich-content";
  if (fillSource === "product_media") return "Берется из медиа товара";
  if (fillSource === "content_manager") return "Заполняет контент-менеджер";
  return "Заполняется как параметр";
}

function systemFeatureValue(feature: ProductFeatureValue, product: ProductData | null) {
  if (!product || !isReadonlySystemFeature(feature)) return "";
  const key = `${normalizeText(feature.code)} ${normalizeText(feature.name)}`.toLowerCase();
  if (key.includes("sku_gt")) return normalizeText(product.sku_gt);
  if (key.includes("sku_pim")) return normalizeText(product.sku_pim);
  if (key.includes("наименование") || key.includes("title")) return normalizeText(product.title);
  return "";
}

function toneForStatus(status: string): "active" | "pending" | "danger" | "neutral" {
  const value = normalizeText(status).toLowerCase();
  if (!value) return "neutral";
  if (value.includes("ok") || value.includes("готов") || value.includes("active") || value.includes("опублик") || value.includes("подключ")) return "active";
  if (value.includes("ошиб") || value.includes("error") || value.includes("расхожд")) return "danger";
  if (value.includes("draft") || value.includes("чернов") || value.includes("pending") || value.includes("модерац")) return "pending";
  return "neutral";
}

function toneForCompetitorSourceStatus(status: string): "active" | "pending" | "danger" | "neutral" {
  const value = normalizeText(status);
  if (value === "confirmed") return "active";
  if (value === "review") return "pending";
  if (value === "scan_error" || value === "no_exact_match") return "danger";
  return "neutral";
}

function ProductWorkspaceSectionNav({
  activeSection,
  onSelect,
  productId,
}: {
  activeSection: SectionId;
  onSelect: (id: SectionId) => void;
  productId: string;
}) {
  return (
    <nav className="productWorkspaceNav" aria-label="Навигация по товару">
      <div className="productWorkspaceNavTitle">Меню товара</div>
      <div className="productWorkspaceNavList">
        {PRODUCT_NAV_ITEMS.map((section) => (
          <button
            key={section.id}
            type="button"
            className={`productWorkspaceNavItem${activeSection === section.id ? " isActive" : ""}`}
            onClick={() => onSelect(section.id)}
          >
            <strong>{section.label}</strong>
            <span>{section.meta}</span>
          </button>
        ))}
        <Link className="productWorkspaceNavItem productWorkspaceNavLink" to={productExportHref(productId)}>
          <strong>Экспорт</strong>
          <span>проверка и payload</span>
        </Link>
      </div>
    </nav>
  );
}

function ProductWorkspaceInspector({
  product,
  categoryPath,
  features,
  variants,
  channels,
  media,
}: {
  product: ProductData;
  categoryPath: string;
  features: ProductFeatureValue[];
  variants: VariantData[];
  channels: ChannelsSummary | null;
  media: ProductMedia[];
}) {
  const filledAttributes = features.filter((feature) => featureValue(feature)).length;
  const emptyAttributes = Math.max(features.length - filledAttributes, 0);
  const activeChannels =
    (channels?.marketplaces.filter((item) => toneForStatus(item.status) === "active").length || 0) +
    (channels?.external_systems.filter((item) => toneForStatus(item.status) === "active").length || 0);

  return (
    <div className="productWorkspaceInspectorStack">
      <InspectorPanel title="Описание" subtitle="Ключевой контекст товара">
        <div className="productWorkspaceKeyValue">
          <span>SKU GT</span>
          <strong>{normalizeText(product.sku_gt) || "Не задан"}</strong>
        </div>
        <div className="productWorkspaceKeyValue">
          <span>SKU PIM</span>
          <strong>{normalizeText(product.sku_pim) || "Не задан"}</strong>
        </div>
        <div className="productWorkspaceKeyValue">
          <span>Категория</span>
          <strong>{categoryPath || "Не задана"}</strong>
        </div>
        <div className="productWorkspaceKeyValue">
          <span>Группа</span>
          <strong>{normalizeText(product.group_id) || "Нет"}</strong>
        </div>
      </InspectorPanel>

      <InspectorPanel title="Readiness" subtitle="Текущее состояние наполнения">
        <div className="productWorkspaceInspectorMetrics">
          <div>
            <span>Заполнено полей</span>
            <strong>{filledAttributes}</strong>
          </div>
          <div>
            <span>Пустых полей</span>
            <strong>{emptyAttributes}</strong>
          </div>
          <div>
            <span>Медиа</span>
            <strong>{media.length}</strong>
          </div>
          <div>
            <span>Каналы готовы</span>
            <strong>{activeChannels}</strong>
          </div>
          <div>
            <span>Варианты</span>
            <strong>{variants.length}</strong>
          </div>
        </div>
      </InspectorPanel>

      <InspectorPanel title="Действия" subtitle="Быстрые переходы">
        <div className="productWorkspaceInspectorActions">
          <Link className="btn primary" to="/products">
            К списку товаров
          </Link>
          {normalizeText(product.group_id) ? (
            <Link className="btn" to="/catalog/groups">
              Открыть группу
            </Link>
          ) : null}
        </div>
      </InspectorPanel>
    </div>
  );
}

function ProductAttributeWorkbench({
  features,
  variants,
  hasInfoModel,
  rawFeatureCount,
  channels,
  parameterFlow,
  productId,
  categoryId,
  selectedKey,
  onSelect,
  onSaveFeatureValue,
  onSaveFeatureValues,
  savingFeatureKey,
  saveNotice,
}: {
  features: ProductFeatureValue[];
  variants: VariantData[];
  hasInfoModel: boolean;
  rawFeatureCount: number;
  channels: ChannelsSummary | null;
  parameterFlow: ProductParameterFlow | null;
  productId: string;
  categoryId: string;
  selectedKey: string;
  onSelect: (key: string) => void;
  onSaveFeatureValue: (feature: ProductFeatureValue, value: string) => Promise<void>;
  onSaveFeatureValues: (updates: FeatureValueUpdate[]) => Promise<void>;
  savingFeatureKey: string;
  saveNotice: string;
}) {
  const selectedFeature = useMemo(() => {
    return features.find((feature, index) => featureKey(feature, index) === selectedKey) || features[0] || null;
  }, [features, selectedKey]);
  const selectedValue = selectedFeature ? featureValue(selectedFeature) : "";
  const selectedFeatureKey = selectedFeature ? featureKey(selectedFeature, features.indexOf(selectedFeature)) : "";
  const selectedIsSystem = isReadonlySystemFeature(selectedFeature);
  const [draftValue, setDraftValue] = useState(selectedValue);
  const sourceEntries = selectedFeature ? sourceEntriesForFeature(selectedFeature) : [];
  const selectedFlowRow = flowRowForFeature(parameterFlow, selectedFeature);
  const projections = selectedFlowRow?.marketplaces || [];
  const filledCount = features.filter((feature) => featureValue(feature)).length;
  const withSourceCount = features.filter((feature) => sourceEntriesForFeature(feature).length).length;
  const noValueCount = features.filter((feature) => !featureValue(feature)).length;
  const exportReadyCount = Number(parameterFlow?.summary?.features_ready || 0) || features.filter((feature) => featureValue(feature) && sourceEntriesForFeature(feature).length).length;
  const attentionCount = Number(parameterFlow?.summary?.features_attention || 0);
  const blockerCount = Number(parameterFlow?.summary?.blockers || parameterFlow?.blockers?.length || 0);
  const blockerItems = (parameterFlow?.blockers || []).slice(0, 6);
  const dimensionBlockers = (parameterFlow?.blockers || []).filter((blocker) =>
    normalizeText(blocker.provider).toLowerCase() === "ozon"
      && normalizeText(blocker.code) === "required_parameter_missing"
      && normalizeText(blocker.parameter).includes("упаковки/товара"),
  );
  const packageDimensionTargets = OZON_PACKAGE_DIMENSION_FIELDS.map((field) => ({
    ...field,
    feature: findFeatureByParameter(features, field.parameter),
  })).filter((field): field is typeof field & { feature: ProductFeatureValue } => Boolean(field.feature));
  const packageEvidence = packageFieldEvidence(packageDimensionTargets);
  const packageSibling = siblingPackageSuggestion(variants, packageDimensionTargets);
  const selectedIsPackageDimension = Boolean(selectedFeature && packageDimensionTargets.some((target) => target.feature === selectedFeature));
  const showPackageDimensionPanel = Boolean(packageDimensionTargets.length && (dimensionBlockers.length || selectedIsPackageDimension));
  const marketplaceEvidenceInProduct = features.some((feature) =>
    sourceEntriesForFeature(feature).some((entry) => isMarketplaceSource(entry.provider) && hasSourceEntryValue(entry)),
  );
  const marketplacePackageChecked = Boolean(dimensionBlockers.length || marketplaceEvidenceInProduct);
  const packageMarketplaceStatus = packageEvidence.fromMarketplace
    ? `${packageEvidence.fromMarketplace}/${packageEvidence.rows.length} из площадок`
    : marketplacePackageChecked
      ? "площадки проверены, размеров нет"
      : "источники еще не проверялись";
  const [dimensionDrafts, setDimensionDrafts] = useState<Record<string, string>>({});
  const conflictCount = features.filter((feature) => {
    const entries = sourceEntriesForFeature(feature);
    const values = new Set(entries.map((item) => item.canonical || item.resolved || item.raw).filter(Boolean).map((item) => item.toLowerCase()));
    return values.size > 1;
  }).length;
  const draftChanged = draftValue !== selectedValue;

  useEffect(() => {
    setDraftValue(selectedValue);
  }, [selectedFeatureKey, selectedValue]);

  useEffect(() => {
    setDimensionDrafts(Object.fromEntries(
      packageDimensionTargets.map((target) => [target.key, featureValue(target.feature)]),
    ));
  }, [features, parameterFlow]);

  const changedDimensionUpdates = packageDimensionTargets
    .map((target) => ({
      feature: target.feature,
      value: normalizeText(dimensionDrafts[target.key]),
      current: featureValue(target.feature),
    }))
    .filter((item) => item.value !== item.current);

  if (!hasInfoModel) {
    return (
      <EmptyState
        title="Инфо-модель не создана"
        description={
          rawFeatureCount
            ? `В товаре сохранено ${rawFeatureCount} сырых параметров из источников, но они не считаются PIM-параметрами до создания инфо-модели категории.`
            : "Сначала соберите и подтвердите инфо-модель категории, после этого здесь появятся PIM-параметры для выгрузки."
        }
      />
    );
  }

  if (!features.length) {
    return <EmptyState title="Инфо-модель не наполнена" description="После выбора категории здесь появятся параметры, их источники и вывод на площадки." />;
  }

  return (
    <div className="productCockpitGrid">
      <aside className="productParamQueue" aria-label="Параметры товара">
        <div className="productParamQueueHead">
          <div>
            <span>Параметры</span>
            <strong>{filledCount}/{features.length}</strong>
          </div>
          <Badge tone={conflictCount ? "danger" : "active"}>{conflictCount ? `${conflictCount} конфликтов` : "без конфликтов"}</Badge>
        </div>
        <div className="productParamExportSummary">
          <span><b>{exportReadyCount}</b> готовы с источником</span>
          <span><b>{withSourceCount}</b> с источником</span>
          <span><b>{blockerCount || attentionCount || noValueCount}</b> {blockerCount || attentionCount ? "блокеры" : "без значения"}</span>
        </div>
        {blockerItems.length ? (
          <div className="productParamBlockerList" aria-label="Блокеры параметров">
            {blockerItems.map((blocker, index) => {
              const targetFeature = findFeatureByParameter(features, blocker.parameter);
              const localKey = targetFeature ? featureKey(targetFeature, features.indexOf(targetFeature)) : "";
              const meta = [
                blocker.provider ? productSourceLabel(blocker.provider) : "",
                blocker.target_id || "",
              ].filter(Boolean).join(" · ");
              if (blocker.code === "empty_value") {
                return (
                  <button
                    key={`${blocker.code}-${blocker.parameter}-${index}`}
                    type="button"
                    className="productParamBlocker"
                    onClick={() => localKey && onSelect(localKey)}
                  >
                    <span>
                      <strong>{productBlockerTitle(blocker)}</strong>
                      <em>{blocker.parameter || "Параметр"}{meta ? ` · ${meta}` : ""}</em>
                    </span>
                    <b>{productBlockerActionLabel(blocker)}</b>
                  </button>
                );
              }
              return (
                <Link
                  key={`${blocker.code}-${blocker.parameter}-${index}`}
                  className="productParamBlocker"
                  to={productSourceFixHref(blocker, categoryId, productId)}
                >
                  <span>
                    <strong>{productBlockerTitle(blocker)}</strong>
                    <em>{blocker.parameter || "Параметр"}{meta ? ` · ${meta}` : ""}</em>
                  </span>
                  <b>{productBlockerActionLabel(blocker)}</b>
                </Link>
              );
            })}
            {blockerCount > blockerItems.length ? (
              <Link className="productParamBlocker isMore" to={`/catalog/exchange?tab=export&product=${encodeURIComponent(productId)}`}>
                <span>
                  <strong>Еще {blockerCount - blockerItems.length}</strong>
                  <em>Полный список в проверке экспорта</em>
                </span>
                <b>Открыть</b>
              </Link>
            ) : null}
          </div>
        ) : null}
        {showPackageDimensionPanel ? (
          <div className="productLogisticsQuickPanel">
            <div className="productLogisticsQuickHead">
              <strong>Габариты для Ozon</strong>
              <span>{dimensionBlockers.length ? `${dimensionBlockers.length} поля мешают экспорту` : "Заполните комплектом, затем вернитесь в проверку экспорта"}</span>
            </div>
            <div className="productLogisticsSourceAudit">
              <div>
                <span>Площадки</span>
                <strong>{packageMarketplaceStatus}</strong>
              </div>
              <div>
                <span>PIM</span>
                <strong>{packageEvidence.filled}/{packageEvidence.rows.length} заполнено</strong>
              </div>
              <div>
                <span>Варианты</span>
                <Link to={`/products/${encodeURIComponent(productId)}?tab=variants`}>
                  {packageSibling ? `${packageSibling.updates.length} можно взять` : "Проверить SKU family"}
                </Link>
              </div>
            </div>
            {marketplacePackageChecked && !packageEvidence.fromMarketplace ? (
              <div className="productLogisticsNotice">
                Market/Ozon уже проверены для выбранных магазинов, но не вернули размеры упаковки. Заполните поля вручную или сверяйтесь с соседним SKU этой линейки.
              </div>
            ) : null}
            {packageSibling ? (
              <div className="productLogisticsSiblingAction">
                <span>
                  <strong>{normalizeText(packageSibling.variant.sku_gt) || normalizeText(packageSibling.variant.sku_pim) || "sibling SKU"}</strong>
                  <em>{packageSibling.updates.map((item) => item.label).join(", ")}</em>
                </span>
                <Button
                  onClick={() => void onSaveFeatureValues(packageSibling.updates.map(({ feature, value }) => ({ feature, value })))}
                  disabled={Boolean(savingFeatureKey)}
                >
                  Взять из sibling SKU
                </Button>
              </div>
            ) : null}
            <div className="productLogisticsQuickGrid">
              {packageDimensionTargets.map((target) => (
                <label key={target.key}>
                  <span>{target.label}</span>
                  <input
                    value={dimensionDrafts[target.key] ?? ""}
                    inputMode="numeric"
                    placeholder={target.placeholder}
                    onChange={(event) => setDimensionDrafts((prev) => ({ ...prev, [target.key]: event.target.value }))}
                  />
                </label>
              ))}
            </div>
            <Button
              variant="primary"
              onClick={() => void onSaveFeatureValues(changedDimensionUpdates.map(({ feature, value }) => ({ feature, value })))}
              disabled={!changedDimensionUpdates.length || Boolean(savingFeatureKey)}
            >
              Сохранить габариты
            </Button>
          </div>
        ) : null}
        <div className="productParamSearchHint">Выберите параметр, чтобы увидеть как он собрался и как уйдет на площадки.</div>
        <div className="productParamList">
          {features.map((feature, index) => {
            const key = featureKey(feature, index);
            const value = featureValue(feature);
            const sourceCount = sourceEntriesForFeature(feature).length;
            return (
              <button
                key={key}
                type="button"
                className={`productParamItem${selectedFeature && key === featureKey(selectedFeature, features.indexOf(selectedFeature)) ? " isActive" : ""}`}
                onClick={() => onSelect(key)}
              >
                <span>
                  <strong>{normalizeText(feature.name) || normalizeText(feature.code) || "Параметр"}</strong>
                  <em title={value || undefined}>{value ? compactText(value, 78) : "Не заполнено"}</em>
                </span>
                <Badge tone={isReadonlySystemFeature(feature) ? "neutral" : qualityTone(!!value)}>{isReadonlySystemFeature(feature) ? "системн." : sourceCount ? `${sourceCount} источн.` : "ручн."}</Badge>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="productParamCanvas">
        {selectedFeature ? (
          <>
            <div className="productParamHero">
              <div>
                <span>Canonical value</span>
                <h2>{normalizeText(selectedFeature.name) || normalizeText(selectedFeature.code) || "Параметр"}</h2>
                <p>{normalizeText(selectedFeature.code) || "код параметра не задан"} · {fieldLayerLabel(selectedFeature.field_layer)}</p>
              </div>
              <div className="productCanonicalValue">
                <span>{featureFillSourceLabel(selectedFeature)}</span>
                <textarea
                  className="productCanonicalInput"
                  value={draftValue}
                  placeholder="Введите значение параметра"
                  disabled={selectedIsSystem || savingFeatureKey === selectedFeatureKey}
                  onChange={(event) => setDraftValue(event.target.value)}
                />
                {selectedIsSystem ? (
                  <div className="productParamEmpty">Системное поле заполняется из карточки товара и не редактируется вручную.</div>
                ) : null}
                <div className="productCanonicalActions">
                  <Button onClick={() => setDraftValue(selectedValue)} disabled={!draftChanged || savingFeatureKey === selectedFeatureKey}>
                    Отменить
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() => void onSaveFeatureValue(selectedFeature, draftValue)}
                    disabled={!draftChanged || selectedIsSystem || savingFeatureKey === selectedFeatureKey}
                  >
                    {savingFeatureKey === selectedFeatureKey ? "Сохраняем" : "Сохранить значение"}
                  </Button>
                </div>
                {saveNotice ? <div className="productParamSaveNotice">{saveNotice}</div> : null}
                {selectedValue.length > 180 ? (
                  <details className="productLongValue">
                    <summary>Показать полный текст</summary>
                    <p>{selectedValue}</p>
                  </details>
                ) : null}
              </div>
            </div>

            <div className="productParamSectionGrid">
              <div className="productParamPanel">
                <div className="productParamPanelHead">
                  <span>Как собралось значение</span>
                  <Badge tone={sourceEntries.length ? "active" : "pending"}>{sourceEntries.length ? "есть источники" : "нет source values"}</Badge>
                </div>
                {sourceEntries.length ? (
                  <div className="productSourceEvidenceList">
                    {sourceEntries.map((entry, index) => (
                      <article key={`${entry.provider}-${entry.store}-${index}`} className="productSourceEvidence">
                        <div>
                          <strong>{entry.provider}</strong>
                          <span>{entry.store}</span>
                        </div>
                        <dl>
                          <div><dt>Raw</dt><dd title={entry.raw || undefined}>{entry.raw ? compactText(entry.raw, 140) : "—"}</dd></div>
                          <div><dt>Resolved</dt><dd title={entry.resolved || undefined}>{entry.resolved ? compactText(entry.resolved, 140) : "—"}</dd></div>
                          <div><dt>Canonical</dt><dd title={entry.canonical || undefined}>{entry.canonical ? compactText(entry.canonical, 140) : "—"}</dd></div>
                        </dl>
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="productParamEmpty">Источник не зафиксирован. Значение сейчас считается ручным или импортированным без детализации.</div>
                )}
              </div>

              <div className="productParamPanel">
                <div className="productParamPanelHead">
                  <span>Вывод на маркетплейсы</span>
                  <Badge tone={selectedValue ? "active" : "pending"}>{selectedValue ? "готово" : "нужно значение"}</Badge>
                </div>
                <div className="productParamExportDiffLead">
                  <span>PIM</span>
                  <strong title={selectedValue || undefined}>{selectedValue ? compactText(selectedValue, 120) : "Не заполнено"}</strong>
                  <em>{sourceEntries.length ? `источников: ${sourceEntries.length}` : "источник не зафиксирован"}</em>
                </div>
                <div className="productMarketplaceProjectionList">
                  {projections.length ? projections.map((projection) => (
                    <article key={`${projection.provider}-${projection.target_id || projection.target_name || projection.label}`} className="productMarketplaceProjection">
                      <div>
                        <strong>{projection.provider_label || projection.provider}</strong>
                        <span>{projection.label || projection.status || "нет статуса"}</span>
                      </div>
                      <code>{projection.output_value || "Не заполнено"}</code>
                      <em>
                        {selectedValue
                          ? `PIM -> ${projection.target_name || projection.target_id || projection.provider_label || projection.provider}`
                          : "нет PIM-значения для экспорта"}
                        {projection.mapping_reason ? ` · ${projection.mapping_reason}` : ""}
                      </em>
                    </article>
                  )) : (
                    <div className="productParamEmpty">
                      Реальных export projections пока нет: проверьте сопоставление параметра с Я.Маркет/Ozon.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function ProductSourcesWorkbench({ features, categoryId }: { features: ProductFeatureValue[]; categoryId?: string }) {
  const rows = features.flatMap((feature) =>
    sourceEntriesForFeature(feature).map((entry) => ({
      feature: normalizeText(feature.name) || normalizeText(feature.code) || "Параметр",
      code: normalizeText(feature.code),
      ...entry,
    })),
  );
  if (!rows.length) {
    const encodedCategoryId = encodeURIComponent(normalizeText(categoryId));
    return (
      <EmptyState
        title="Источники пока не связаны"
        description="Чтобы здесь появилась трассировка по параметрам, сначала сопоставьте категорию, поля площадок и конкурентные источники."
        action={
          <div className="productWorkspaceEmptyActions">
            {encodedCategoryId ? (
              <>
                <Link className="btn primary" to={`/sources?tab=params&category=${encodedCategoryId}`}>Открыть сопоставление</Link>
                <Link className="btn" to={`/sources?tab=sources&category=${encodedCategoryId}`}>Связать источники</Link>
                <Link className="btn" to={`/templates/${encodedCategoryId}`}>Собрать инфо-модель</Link>
              </>
            ) : (
              <Link className="btn primary" to="/sources?tab=sources">Открыть сопоставление</Link>
            )}
          </div>
        }
      />
    );
  }
  return (
    <div className="productWorkspaceTableWrap">
      <table className="productWorkspaceTable">
        <thead>
          <tr>
            <th>Параметр</th>
            <th>Источник</th>
            <th>Raw</th>
            <th>Resolved</th>
            <th>Canonical</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.provider}-${row.store}-${row.code}-${index}`}>
              <td>{row.feature}</td>
              <td>{row.provider} / {row.store}</td>
              <td>{row.raw || "—"}</td>
              <td>{row.resolved || "—"}</td>
              <td>{row.canonical || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ProductValidationWorkbench({
  features,
  media,
  description,
  exportHref,
  onOpenFeature,
  onOpenMedia,
  onOpenCompetitors,
}: {
  features: ProductFeatureValue[];
  media: ProductMedia[];
  description: string;
  exportHref: string;
  onOpenFeature: (feature: ProductFeatureValue) => void;
  onOpenMedia: () => void;
  onOpenCompetitors: () => void;
}) {
  const missing = features.filter((feature) => !featureValue(feature));
  const requiredMissing = missing.filter((feature) => feature.required);
  const optionalMissing = missing.filter((feature) => !feature.required);
  const filled = features.length - missing.length;
  const blockers = [
    ...requiredMissing.map((feature) => ({
      key: `field:${featureKey(feature, features.indexOf(feature))}`,
      title: featureLabel(feature),
      meta: featureGroup(feature),
      action: "Заполнить параметр",
      onClick: () => onOpenFeature(feature),
    })),
    ...(!media.length
      ? [{
          key: "media",
          title: "Медиа товара",
          meta: "нет изображений в S3",
          action: "Открыть медиа",
          onClick: onOpenMedia,
        }]
      : []),
    ...(!normalizeText(description)
      ? [{
          key: "description",
          title: "Описание товара",
          meta: "нет текста для карточки",
          action: "Найти источник",
          onClick: onOpenCompetitors,
        }]
      : []),
  ];

  const optionalByGroup = optionalMissing.reduce((acc, feature) => {
    const group = featureGroup(feature);
    acc.set(group, [...(acc.get(group) || []), feature]);
    return acc;
  }, new Map<string, ProductFeatureValue[]>());
  const groups = Array.from(optionalByGroup.entries())
    .map(([group, items]) => ({ group, items }))
    .sort((a, b) => b.items.length - a.items.length);

  return (
    <div className="productValidationWorkbench">
      <div className="productWorkspaceValidationGrid">
        <div className="productWorkspaceValidationCard">
          <span>Готовность полей</span>
          <strong>{features.length ? `${filled}/${features.length}` : "0/0"}</strong>
        </div>
        <div className={`productWorkspaceValidationCard${requiredMissing.length ? " isDanger" : " isReady"}`}>
          <span>Обязательные</span>
          <strong>{requiredMissing.length ? `${requiredMissing.length} заполнить` : "Готово"}</strong>
        </div>
        <div className={`productWorkspaceValidationCard${media.length ? " isReady" : " isDanger"}`}>
          <span>Медиа</span>
          <strong>{media.length ? `${media.length} фото` : "Пусто"}</strong>
        </div>
        <div className={`productWorkspaceValidationCard${normalizeText(description) ? " isReady" : " isPending"}`}>
          <span>Описание</span>
          <strong>{normalizeText(description) ? "Готово" : "Пусто"}</strong>
        </div>
      </div>

      <div className="productValidationColumns">
        <section className="productValidationPanel">
          <div className="productValidationPanelHead">
            <div>
              <span>Что блокирует выгрузку</span>
              <strong>{blockers.length ? `${blockers.length} задач` : "Блокеров нет"}</strong>
            </div>
            <Badge tone={blockers.length ? "danger" : "active"}>{blockers.length ? "нужно исправить" : "готово"}</Badge>
          </div>
          <div className="productValidationExportAction">
            <Link className="btn primary" to={exportHref}>Проверить экспорт SKU</Link>
            <span>Readiness batch покажет реальные блокеры площадок и прямые места исправления.</span>
          </div>
          {blockers.length ? (
            <div className="productValidationTaskList">
              {blockers.slice(0, 8).map((item) => (
                <article key={item.key} className="productValidationTask">
                  <div>
                    <strong>{item.title}</strong>
                    <span>{item.meta}</span>
                  </div>
                  <Button onClick={item.onClick}>{item.action}</Button>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Критичных блокеров нет" description="Можно переходить к проверке площадок и экспортной готовности." />
          )}
        </section>

        <section className="productValidationPanel">
          <div className="productValidationPanelHead">
            <div>
              <span>Пустые необязательные поля</span>
              <strong>{optionalMissing.length}</strong>
            </div>
            <Badge tone={optionalMissing.length ? "pending" : "active"}>{optionalMissing.length ? "можно улучшить" : "готово"}</Badge>
          </div>
          {groups.length ? (
            <div className="productValidationGroupList">
              {groups.slice(0, 7).map(({ group, items }) => (
                <article key={group} className="productValidationGroup">
                  <div>
                    <strong>{group}</strong>
                    <span>{items.slice(0, 4).map(featureLabel).join(", ")}</span>
                  </div>
                  <Badge tone="neutral">{items.length}</Badge>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState title="Дополнительные поля заполнены" description="По необязательным параметрам нет явных пропусков." />
          )}
        </section>
      </div>
    </div>
  );
}

function ProductCreateFlowPreview() {
  const steps = [
    ["01", "Базовые данные", "название, SKU, бренд, статус"],
    ["02", "Категория", "выбор конечной категории и инфо-модели"],
    ["03", "Варианты", "группа SKU, параметры схлопывания"],
    ["04", "Источники", "импорт, Excel, конкурентные links"],
    ["05", "Preview", "как товар выглядит в PIM и на площадках"],
    ["06", "Создание", "создать SKU и открыть cockpit"],
  ];
  return (
    <div className="productCreateFlowPreview">
      {steps.map(([num, title, text]) => (
        <article key={num}>
          <span>{num}</span>
          <strong>{title}</strong>
          <p>{text}</p>
        </article>
      ))}
    </div>
  );
}

function ProductCommerceHero({
  product,
  categoryPath,
  features,
  media,
  variants,
  channels,
  analogs,
  accessories,
}: {
  product: ProductData;
  categoryPath: string;
  features: ProductFeatureValue[];
  media: ProductMedia[];
  variants: VariantData[];
  channels: ChannelsSummary | null;
  analogs: ProductRelation[];
  accessories: ProductRelation[];
}) {
  const filledAttributes = features.filter((feature) => featureValue(feature)).length;
  const importantFeatures = features.filter((feature) => featureValue(feature)).slice(0, 6);
  const cover = media[0] || null;
  const activeChannels =
    (channels?.marketplaces.filter((item) => toneForStatus(item.status) === "active").length || 0) +
    (channels?.external_systems.filter((item) => toneForStatus(item.status) === "active").length || 0);
  const readinessItems = [
    { label: "Параметры", value: `${filledAttributes}/${features.length || 0}`, state: filledAttributes ? "isReady" : "isPending" },
    { label: "Медиа", value: String(media.length), state: media.length ? "isReady" : "isPending" },
    { label: "Каналы", value: String(activeChannels), state: activeChannels ? "isReady" : "isPending" },
    { label: "Связи", value: String(analogs.length + accessories.length), state: analogs.length + accessories.length ? "isReady" : "isPending" },
  ];

  return (
    <Card className="productCommerceCard">
      <div className="productCommerceGrid">
        <section className="productCommerceGallery" aria-label="Медиа товара">
          <div className="productCommerceImageStage">
            {cover ? (
              <img src={toRenderableMediaUrl(cover.url)} alt={cover.caption || product.title} />
            ) : (
              <div className="productCommerceImagePlaceholder">
                <span>SKU</span>
                <strong>{normalizeText(product.sku_gt) || normalizeText(product.sku_pim) || product.id}</strong>
              </div>
            )}
          </div>
          <div className="productCommerceThumbRow">
            {(media.length ? media.slice(0, 5) : [null, null, null]).map((item, index) => (
              <div key={item?.url || `empty-${index}`} className={`productCommerceThumb${item ? "" : " isEmpty"}`}>
                {item ? <img src={toRenderableMediaUrl(item.url)} alt={item.caption || `${product.title} ${index + 1}`} /> : <span>{index + 1}</span>}
              </div>
            ))}
          </div>
        </section>

        <section className="productCommerceSummary">
          <div className="productCommerceBreadcrumb">{categoryPath || "Категория не задана"}</div>
          <div className="productCommerceTitleRow">
            <h1>{product.title}</h1>
            <Badge tone={toneForStatus(normalizeText(product.status))}>{normalizeText(product.status) || "draft"}</Badge>
          </div>
          <div className="productCommerceLead">
            <span>{inferBrand(product.title, features)}</span>
            <span>SKU GT: {normalizeText(product.sku_gt) || "—"}</span>
            <span>SKU PIM: {normalizeText(product.sku_pim) || "—"}</span>
            <span>{variants.length ? `${variants.length} вариантов` : "без variant-family"}</span>
          </div>

          <div className="productCommerceSpecGrid">
            {importantFeatures.length ? (
              importantFeatures.map((feature, index) => (
                <div key={featureKey(feature, index)} className="productCommerceSpec">
                  <span>{normalizeText(feature.name) || normalizeText(feature.code) || "Параметр"}</span>
                  <strong>{featureValue(feature)}</strong>
                </div>
              ))
            ) : (
              <div className="productCommerceSpec isWide">
                <span>Параметры</span>
                <strong>Пока не заполнены</strong>
              </div>
            )}
          </div>
        </section>

        <aside className="productCommerceReadiness" aria-label="Готовность карточки">
          <div className="productCommerceReadinessHead">
            <span>Готовность</span>
            <strong>{filledAttributes || media.length || activeChannels ? "В работе" : "Черновик"}</strong>
          </div>
          <div className="productCommerceReadinessList">
            {readinessItems.map((item) => (
              <div key={item.label} className={`productCommerceReadinessItem ${item.state}`}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </Card>
  );
}

function ProductWorkspaceSkeleton() {
  return (
    <div className="page-shell productWorkspacePage">
      <div className="productWorkspaceTopbar isSkeleton" aria-hidden="true">
        <div className="productWorkspaceTopbarMain">
          <div className="productWorkspaceSkeletonLine productWorkspaceSkeletonEyebrow" />
          <div className="productWorkspaceSkeletonLine productWorkspaceSkeletonTitle" />
          <div className="productWorkspaceMetaRow">
            <div className="productWorkspaceSkeletonChip" />
            <div className="productWorkspaceSkeletonChip" />
            <div className="productWorkspaceSkeletonChip isWide" />
          </div>
        </div>
        <div className="productWorkspaceTopbarActions">
          <div className="productWorkspaceSkeletonButton" />
          <div className="productWorkspaceSkeletonButton isGhost" />
        </div>
      </div>

      <WorkspaceFrame
        className="productWorkspaceLayout"
        sidebar={
          <div className="productWorkspaceNav isSkeleton" aria-hidden="true">
            <div className="productWorkspaceSkeletonLine productWorkspaceSkeletonNavTitle" />
            <div className="productWorkspaceNavList">
              {Array.from({ length: 7 }).map((_, index) => (
                <div key={index} className="productWorkspaceSkeletonNavItem" />
              ))}
            </div>
          </div>
        }
        main={
          <div className="productWorkspaceMainStack" aria-hidden="true">
            <Card className="productWorkspaceHeroCard isSkeleton">
              <div className="productWorkspaceHeroGrid">
                <div className="productWorkspaceSkeletonBlock isHeroCopy" />
                <div className="productWorkspaceHeroStats">
                  {Array.from({ length: 3 }).map((_, index) => (
                    <div key={index} className="productWorkspaceSkeletonMetric" />
                  ))}
                </div>
              </div>
            </Card>
            <Card className="isSkeleton">
              <div className="productWorkspaceSkeletonCanvas" />
            </Card>
          </div>
        }
        inspector={
          <div className="productWorkspaceInspectorStack" aria-hidden="true">
            <InspectorPanel title="Описание" subtitle="Загрузка товара">
              <div className="productWorkspaceSkeletonInspector" />
            </InspectorPanel>
            <InspectorPanel title="Readiness" subtitle="Загрузка контекста">
              <div className="productWorkspaceSkeletonInspector" />
            </InspectorPanel>
          </div>
        }
      />
    </div>
  );
}

function ProductWorkspaceFeature() {
  const { productId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [product, setProduct] = useState<ProductData | null>(null);
  const [infoModel, setInfoModel] = useState<ProductInfoModel | null>(null);
  const [variants, setVariants] = useState<VariantData[]>([]);
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [channels, setChannels] = useState<ChannelsSummary | null>(null);
  const [parameterFlow, setParameterFlow] = useState<ProductParameterFlow | null>(null);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionId>(() => sectionFromTab(searchParams.get("tab")));
  const [selectedFeatureKey, setSelectedFeatureKey] = useState("");
  const [competitorProductId, setCompetitorProductId] = useState("");
  const [competitorSkuStatuses, setCompetitorSkuStatuses] = useState<Record<string, CompetitorSkuStatus>>({});
  const [competitorSkuQuery, setCompetitorSkuQuery] = useState("");
  const [competitorSkuFilter, setCompetitorSkuFilter] = useState<"all" | CompetitorSkuStatus["tone"]>("all");
  const [competitorSelectedIds, setCompetitorSelectedIds] = useState<string[]>([]);
  const [competitorBulkRunning, setCompetitorBulkRunning] = useState(false);
  const [competitorBulkConfirming, setCompetitorBulkConfirming] = useState(false);
  const [competitorBulkEnriching, setCompetitorBulkEnriching] = useState(false);
  const [competitorBulkNotice, setCompetitorBulkNotice] = useState("");
  const [competitorBulkRun, setCompetitorBulkRun] = useState<CompetitorDiscoveryRunResp["run"] | null>(null);
  const [reloadVersion, setReloadVersion] = useState(0);
  const [mediaSaving, setMediaSaving] = useState(false);
  const [mediaNotice, setMediaNotice] = useState("");
  const [featureSavingKey, setFeatureSavingKey] = useState("");
  const [featureNotice, setFeatureNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    let channelsAbort: AbortController | null = null;
    async function run() {
      setLoading(true);
      setError("");
      setProduct(null);
      setInfoModel(null);
      setVariants([]);
      setNodes([]);
      setChannels(null);
      setParameterFlow(null);
      setChannelsLoading(false);
      setCompetitorProductId("");
      setCompetitorSkuStatuses({});
      setCompetitorSkuQuery("");
      setCompetitorSkuFilter("all");
      setCompetitorSelectedIds([]);
      setCompetitorBulkRunning(false);
      setCompetitorBulkNotice("");
      setCompetitorBulkRun(null);
      setMediaSaving(false);
      setMediaNotice("");
      setFeatureSavingKey("");
      setFeatureNotice("");
      let shellResolved = false;
      let fullProductResolved = false;
      let summaryProduct: ProductData | null = null;
      void api<{ nodes: CatalogNode[] }>("/catalog/nodes")
        .then((nodesResponse) => {
          if (!cancelled) setNodes(Array.isArray(nodesResponse.nodes) ? nodesResponse.nodes : []);
        })
        .catch(() => {
          if (!cancelled) setNodes([]);
        });
      const summaryPromise = api<ProductWorkspaceSummaryResp>(`/catalog/products/search?ids=${encodeURIComponent(productId)}&limit=1`)
        .then((summaryResponse) => {
          const summary = Array.isArray(summaryResponse.items) ? summaryResponse.items[0] : null;
          if (!summary || cancelled) return null;
          shellResolved = true;
          summaryProduct = {
            id: String(summary.id || productId),
            title: normalizeText(summary.title) || normalizeText(summary.name) || productId,
            sku_pim: normalizeText(summary.sku_pim) || undefined,
            sku_gt: normalizeText(summary.sku_gt) || undefined,
            category_id: normalizeText(summary.category_id) || undefined,
            group_id: normalizeText(summary.group_id) || undefined,
            status: "draft",
            content: summary.content && typeof summary.content === "object"
              ? summary.content
              : normalizeText(summary.preview_url)
                ? {
                    media: [{ url: normalizeText(summary.preview_url) }],
                    media_images: [{ url: normalizeText(summary.preview_url) }],
                  }
                : {},
          };
          if (!fullProductResolved) {
            setProduct(summaryProduct);
            setLoading(false);
          }
          return summaryProduct;
        })
        .catch(() => {
          shellResolved = false;
          return null;
        });
      try {
        const productResponse = await api<ProductResponse>(`/products/${productId}`);
        if (cancelled) return;
        fullProductResolved = true;
        const summary = summaryProduct || await summaryPromise;
        const mergedProduct = {
          ...(summary || {}),
          ...productResponse.product,
          title: normalizeText(productResponse.product.title) || normalizeText(summary?.title) || productId,
          sku_pim: normalizeText(productResponse.product.sku_pim) || normalizeText(summary?.sku_pim) || undefined,
          sku_gt: normalizeText(productResponse.product.sku_gt) || normalizeText(summary?.sku_gt) || undefined,
          category_id: normalizeText(productResponse.product.category_id) || normalizeText(summary?.category_id) || undefined,
          group_id: normalizeText(productResponse.product.group_id) || normalizeText(summary?.group_id) || undefined,
        };
        const mergedGroupId = normalizeText(mergedProduct.group_id);
        setProduct(mergedProduct);
        setInfoModel(productResponse.info_model || null);
        let nextVariants = Array.isArray(productResponse.variants) ? productResponse.variants : [];
        if (mergedGroupId && nextVariants.length === 0) {
          try {
            const groupResponse = await api<{ items?: VariantData[] }>(`/product-groups/${encodeURIComponent(mergedGroupId)}`);
            nextVariants = (groupResponse.items || []).filter((item) => normalizeText(item.id) !== normalizeText(mergedProduct.id));
          } catch {
            nextVariants = [];
          }
        }
        setVariants(nextVariants);
        setLoading(false);
        try {
          if (!cancelled) setChannelsLoading(true);
          channelsAbort = new AbortController();
          const channelsTimer = window.setTimeout(() => channelsAbort?.abort(), 5000);
          let channelsResponse: ChannelsSummary | null = null;
          try {
            channelsResponse = await api<ChannelsSummary>(`/products/${productId}/channels-summary`, {
              signal: channelsAbort.signal,
            });
          } finally {
            window.clearTimeout(channelsTimer);
          }
          if (!cancelled) setChannels(channelsResponse);
        } catch {
          if (!cancelled) setChannels(null);
        } finally {
          if (!cancelled) setChannelsLoading(false);
        }
        try {
          const flowResponse = await api<ProductParameterFlow>(`/products/${productId}/parameter-flow`);
          if (!cancelled) setParameterFlow(flowResponse);
        } catch {
          if (!cancelled) setParameterFlow(null);
        }
      } catch (err) {
        if (cancelled) return;
        if (!shellResolved) {
          setError(err instanceof Error ? err.message : "Не удалось загрузить товар.");
          setLoading(false);
        }
      }
    }
    void run();
    return () => {
      cancelled = true;
      channelsAbort?.abort();
    };
  }, [productId, reloadVersion]);

  useEffect(() => {
    setActiveSection(sectionFromTab(searchParams.get("tab")));
  }, [searchParams]);

  const rawFeatures = useMemo(() => {
    return (product?.content?.features || []).filter((feature) => isProductFeatureCode(feature.code || feature.name));
  }, [product]);
  const templateFeatureCodes = useMemo(() => {
    const attrs = Array.isArray(infoModel?.attributes) ? infoModel?.attributes || [] : [];
    return new Set(attrs.flatMap((attr) => [featureIdentity(attr.code), featureIdentity(attr.name)]).filter(Boolean));
  }, [infoModel]);
  const templateFeatureByIdentity = useMemo(() => {
    const attrs = Array.isArray(infoModel?.attributes) ? infoModel?.attributes || [] : [];
    const out = new Map<string, ProductFeatureValue>();
    for (const attr of attrs) {
      const codeKey = featureIdentity(attr.code);
      const nameKey = featureIdentity(attr.name);
      if (codeKey) out.set(codeKey, attr);
      if (nameKey) out.set(nameKey, attr);
    }
    return out;
  }, [infoModel]);
  const hasInfoModel = Boolean(infoModel?.has_template);
  const features = useMemo(() => {
    if (!hasInfoModel) return [];
    if (!templateFeatureCodes.size) return rawFeatures;
    const merged = rawFeatures.filter((feature) => {
      const code = featureIdentity(feature.code);
      const name = featureIdentity(feature.name);
      return (code && templateFeatureCodes.has(code)) || (name && templateFeatureCodes.has(name));
    }).map((feature) => {
      const meta = templateFeatureByIdentity.get(featureIdentity(feature.code)) || templateFeatureByIdentity.get(featureIdentity(feature.name));
      const mergedFeature = meta ? { ...meta, ...feature, value: feature.value, source_values: feature.source_values } : feature;
      const systemValue = systemFeatureValue(mergedFeature, product);
      return systemValue && !normalizeText(mergedFeature.value) ? { ...mergedFeature, value: systemValue } : mergedFeature;
    });
    const used = new Set(merged.flatMap((feature) => [featureIdentity(feature.code), featureIdentity(feature.name)]).filter(Boolean));
    for (const attr of templateFeatureByIdentity.values()) {
      const key = featureIdentity(attr.code) || featureIdentity(attr.name);
      if (key && !used.has(key)) {
        merged.push({ ...attr, value: systemFeatureValue(attr, product) });
        used.add(key);
      }
    }
    return merged;
  }, [hasInfoModel, product, rawFeatures, templateFeatureCodes, templateFeatureByIdentity]);
  const media = useMemo(() => flattenMedia(product?.content), [product]);
  const descriptionSources = useMemo(() => descriptionSourceEntries(product?.content), [product]);
  const selectedMediaCount = useMemo(() => media.filter((item) => item.selected !== false).length, [media]);
  const selectedReviewMediaCount = useMemo(
    () => media.filter((item) => item.selected !== false && isMediaWaitingForReview(item)).length,
    [media],
  );
  const categoryPath = useMemo(() => buildCategoryPath(nodes, product?.category_id), [nodes, product?.category_id]);
  const competitorGroupItems = useMemo(() => {
    if (!product || !normalizeText(product.group_id)) return [];
    const byId = new Map<string, VariantData | ProductData>();
    byId.set(product.id, product);
    for (const variant of variants) {
      if (normalizeText(variant.id)) byId.set(variant.id, variant);
    }
    return Array.from(byId.values());
  }, [product, variants]);
  const selectedCompetitorItem = useMemo(() => {
    return competitorGroupItems.find((item) => item.id === competitorProductId) || competitorGroupItems[0] || product;
  }, [competitorGroupItems, competitorProductId, product]);
  const filteredCompetitorGroupItems = useMemo(() => {
    const q = normalizeText(competitorSkuQuery).toLowerCase();
    return competitorGroupItems.filter((item) => {
      const status = competitorSkuStatuses[item.id];
      if (competitorSkuFilter !== "all" && status?.tone !== competitorSkuFilter) return false;
      if (!q) return true;
      return [item.id, item.title, item.sku_gt, item.sku_pim].some((value) => normalizeText(value).toLowerCase().includes(q));
    });
  }, [competitorGroupItems, competitorSkuFilter, competitorSkuQuery, competitorSkuStatuses]);
  const filteredCompetitorIds = useMemo(() => {
    return filteredCompetitorGroupItems.map((item) => normalizeText(item.id)).filter(Boolean);
  }, [filteredCompetitorGroupItems]);
  const selectedCompetitorSet = useMemo(() => new Set(competitorSelectedIds), [competitorSelectedIds]);
  const selectedVisibleCompetitorIds = useMemo(() => {
    return filteredCompetitorIds.filter((id) => selectedCompetitorSet.has(id));
  }, [filteredCompetitorIds, selectedCompetitorSet]);
  const justCreated = searchParams.get("created") === "1";
  const nextAction = useMemo(() => product
    ? buildProductNextAction({ product, infoModel, features, media, channels })
    : null,
    [channels, features, infoModel, media, product],
  );
  const lineageSummary = useMemo(() => buildProductLineageSummary({ features, media, channels }), [channels, features, media]);

  useEffect(() => {
    if (!product?.id) return;
    try {
      window.localStorage.setItem(PRODUCT_CONTEXT_CACHE_KEY, JSON.stringify({
        productId: product.id,
        categoryId: normalizeText(product.category_id),
        categoryName: categoryPath || normalizeText(product.category_id),
        title: normalizeText(product.title),
        skuGt: normalizeText(product.sku_gt),
        updatedAt: new Date().toISOString(),
      }));
    } catch {
      // URL params still carry context when localStorage is unavailable.
    }
  }, [categoryPath, product?.category_id, product?.id, product?.sku_gt, product?.title]);

  async function saveMediaImages(nextMedia: ProductMedia[]) {
    if (!product) return;
    const orderedMedia = nextMedia.map((item, index) => ({
      ...item,
      order: index,
      export_order: item.export_order ?? index,
    }));
    const nextContent: ProductContent = {
      ...(product.content || {}),
      media_images: orderedMedia,
      media: orderedMedia,
    };
    const optimisticProduct = { ...product, content: nextContent };
    setProduct(optimisticProduct);
    setMediaSaving(true);
    setMediaNotice("");
    try {
      const response = await api<{ product: ProductData }>(`/products/${encodeURIComponent(product.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ content: nextContent }),
      });
      setProduct(response.product || optimisticProduct);
      setMediaNotice("Порядок и выбор медиа сохранены.");
    } catch (err) {
      setProduct(product);
      setMediaNotice(err instanceof Error ? err.message : "Не удалось сохранить медиа.");
    } finally {
      setMediaSaving(false);
    }
  }

  async function saveFeatureValues(updates: FeatureValueUpdate[]) {
    if (!product) return;
    const cleanUpdates = updates
      .filter((item) => item.feature && !isReadonlySystemFeature(item.feature))
      .map((item) => ({ feature: item.feature, value: normalizeText(item.value) }));
    if (!cleanUpdates.length) return;
    const currentFeatures = Array.isArray(product.content?.features) ? product.content?.features || [] : [];
    const matchedUpdateIndexes = new Set<number>();
    const nextFeatures = currentFeatures.map((item) => {
      const itemCode = featureIdentity(item.code);
      const itemName = featureIdentity(item.name);
      const updateIndex = cleanUpdates.findIndex(({ feature }) => {
        const targetCode = featureIdentity(feature.code);
        const targetName = featureIdentity(feature.name);
        return (targetCode && itemCode === targetCode) || (targetName && itemName === targetName) || (targetCode && itemName === targetCode) || (targetName && itemCode === targetName);
      });
      if (updateIndex < 0) return item;
      matchedUpdateIndexes.add(updateIndex);
      const update = cleanUpdates[updateIndex];
      return {
        ...item,
        ...update.feature,
        source_values: item.source_values || update.feature.source_values,
        value: update.value,
      };
    });
    cleanUpdates.forEach((update, index) => {
      if (!matchedUpdateIndexes.has(index)) {
        nextFeatures.push({
          ...update.feature,
          value: update.value,
        });
      }
    });
    if (nextFeatures.length === currentFeatures.length) {
      let changed = false;
      for (let index = 0; index < nextFeatures.length; index += 1) {
        if (nextFeatures[index] !== currentFeatures[index]) {
          changed = true;
          break;
        }
      }
      if (!changed) return;
    }
    const nextContent: ProductContent = {
      ...(product.content || {}),
      features: nextFeatures,
    };
    const optimisticProduct = { ...product, content: nextContent };
    const firstFeature = cleanUpdates[0].feature;
    const savingKey = cleanUpdates.length > 1 ? "bulk:features" : featureKey(firstFeature, features.indexOf(firstFeature) >= 0 ? features.indexOf(firstFeature) : 0);
    setProduct(optimisticProduct);
    setFeatureSavingKey(savingKey);
    setFeatureNotice("");
    try {
      const response = await api<{ product: ProductData }>(`/products/${encodeURIComponent(product.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ content: nextContent }),
      });
      const nextProduct = response.product || optimisticProduct;
      setProduct(nextProduct);
      setFeatureNotice(cleanUpdates.length > 1 ? "Значения сохранены в PIM." : cleanUpdates[0].value ? "Значение сохранено в PIM." : "Значение очищено.");
      try {
        const flowResponse = await api<ProductParameterFlow>(`/products/${product.id}/parameter-flow`);
        setParameterFlow(flowResponse);
      } catch {
        setParameterFlow(null);
      }
    } catch (err) {
      setProduct(product);
      setFeatureNotice(err instanceof Error ? err.message : "Не удалось сохранить значение.");
    } finally {
      setFeatureSavingKey("");
    }
  }

  async function saveFeatureValue(feature: ProductFeatureValue, value: string) {
    await saveFeatureValues([{ feature, value }]);
  }

  async function deleteProduct() {
    if (!product) return;
    const title = normalizeText(product.title) || normalizeText(product.sku_gt) || product.id;
    if (!window.confirm(`Удалить товар "${title}" безвозвратно?`)) return;
    setError("");
    try {
      await api(`/products/${encodeURIComponent(product.id)}`, { method: "DELETE" });
      navigate("/products");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить товар.");
    }
  }

  function toggleMediaForExport(index: number, selected: boolean) {
    const nextMedia = media.map((item, itemIndex) => (itemIndex === index ? { ...item, selected } : item));
    void saveMediaImages(nextMedia);
  }

  function moveMediaForExport(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= media.length) return;
    const nextMedia = [...media];
    const [item] = nextMedia.splice(index, 1);
    nextMedia.splice(target, 0, item);
    const orderedMedia = nextMedia.map((mediaItem, orderIndex) => ({
      ...mediaItem,
      order: orderIndex,
      export_order: orderIndex,
    }));
    void saveMediaImages(orderedMedia);
  }

  function excludeReviewMediaFromExport() {
    const nextMedia = media.map((item) => (
      isMediaWaitingForReview(item) ? { ...item, selected: false } : item
    ));
    void saveMediaImages(nextMedia);
  }
  const allVisibleCompetitorsSelected = filteredCompetitorIds.length > 0 && selectedVisibleCompetitorIds.length === filteredCompetitorIds.length;
  const competitorSkuStatusCounts = useMemo(() => {
    const counts = { all: competitorGroupItems.length, active: 0, pending: 0, danger: 0, neutral: 0 };
    for (const item of competitorGroupItems) {
      const tone = competitorSkuStatuses[item.id]?.tone || "neutral";
      counts[tone] += 1;
    }
    return counts;
  }, [competitorGroupItems, competitorSkuStatuses]);

  const accessories = useMemo(() => {
    return (product?.content?.related || []).filter((item) => normalizeText(item.name) || normalizeText(item.sku) || normalizeText(item.sku_gt));
  }, [product]);

  const analogs = useMemo(() => {
    return (product?.content?.analogs || []).filter((item) => normalizeText(item.name) || normalizeText(item.sku) || normalizeText(item.sku_gt));
  }, [product]);

  useEffect(() => {
    if (!features.length) {
      setSelectedFeatureKey("");
      return;
    }
    const requestedParameter = normalizeText(searchParams.get("parameter"));
    if (requestedParameter) {
      const requestedFeature = findFeatureByParameter(features, requestedParameter);
      if (requestedFeature) {
        const requestedIndex = features.indexOf(requestedFeature);
        setSelectedFeatureKey(featureKey(requestedFeature, requestedIndex >= 0 ? requestedIndex : 0));
        return;
      }
    }
    setSelectedFeatureKey((prev) => {
      if (prev && features.some((feature, index) => featureKey(feature, index) === prev)) return prev;
      return featureKey(features[0], 0);
    });
  }, [features, searchParams]);

  useEffect(() => {
    if (!competitorGroupItems.length) {
      setCompetitorProductId("");
      return;
    }
    setCompetitorProductId((prev) => {
      if (prev && competitorGroupItems.some((item) => item.id === prev)) return prev;
      return product?.id || competitorGroupItems[0].id;
    });
  }, [competitorGroupItems, product?.id]);

  useEffect(() => {
    if (activeSection !== "competitors" || competitorGroupItems.length <= 1) {
      setCompetitorSkuStatuses({});
      return;
    }
    let cancelled = false;
    const ids = competitorGroupItems.map((item) => normalizeText(item.id)).filter(Boolean);
    setCompetitorSkuStatuses(Object.fromEntries(ids.map((id) => [id, { label: "Проверяем", detail: "загрузка статусов", tone: "neutral" as const }])));

    async function run() {
      const entries = await Promise.all(
        ids.map(async (id) => {
          try {
            const response = await api<ProductCompetitorContextResp>(`/competitor-mapping/discovery/products/${encodeURIComponent(id)}`);
            const summaries = response.source_summaries || [];
            const confirmed = Number(response.counts?.confirmed_links || 0) || summaries.reduce((sum, item) => sum + Number(item.confirmed_count || 0), 0);
            const review = Number(response.counts?.needs_review || 0) || summaries.reduce((sum, item) => sum + Number(item.actionable_count || 0), 0);
            const scanned = summaries.some((item) => normalizeText(item.last_scanned_at));
            const hasError = summaries.some((item) => ["scan_error", "no_exact_match"].includes(normalizeText(item.status)));
            const detail = summaries.length
              ? summaries.map((item) => `${item.source_id === "restore" ? "re-store" : item.source_id || "источник"}: ${item.label || "нет статуса"}`).join(" · ")
              : "источники еще не проверялись";
            const sourceChips = summaries.map((item) => ({
              id: normalizeText(item.source_id) || "source",
              label: item.source_id === "restore" ? "re-store" : normalizeText(item.source_id) || "источник",
              tone: toneForCompetitorSourceStatus(normalizeText(item.status)),
            }));
            if (confirmed > 0) return [id, { label: `${confirmed} подтверждено`, detail, tone: "active" as const, sources: sourceChips }] as const;
            if (review > 0) return [id, { label: `${review} кандидат`, detail, tone: "pending" as const, sources: sourceChips }] as const;
            if (hasError) return [id, { label: "нет точного", detail, tone: "danger" as const, sources: sourceChips }] as const;
            if (scanned) return [id, { label: "нет кандидатов", detail, tone: "neutral" as const, sources: sourceChips }] as const;
            return [id, { label: "не сканировали", detail, tone: "neutral" as const, sources: sourceChips }] as const;
          } catch {
            return [id, { label: "ошибка", detail: "не удалось получить статус", tone: "danger" as const }] as const;
          }
        }),
      );
      if (!cancelled) setCompetitorSkuStatuses(Object.fromEntries(entries));
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [activeSection, competitorGroupItems, reloadVersion]);

  useEffect(() => {
    setCompetitorSelectedIds((prev) => {
      if (!prev.length) return prev;
      const allowed = new Set(competitorGroupItems.map((item) => normalizeText(item.id)).filter(Boolean));
      const next = prev.filter((id) => allowed.has(id));
      return next.length === prev.length ? prev : next;
    });
  }, [competitorGroupItems]);

  useEffect(() => {
    const runId = normalizeText(competitorBulkRun?.id);
    const status = normalizeText(competitorBulkRun?.status);
    if (!runId || !["queued", "running"].includes(status)) return;

    let cancelled = false;
    const timer = window.setInterval(() => {
      void api<CompetitorDiscoveryRunResp>(`/competitor-mapping/discovery/runs/${encodeURIComponent(runId)}`)
        .then((response) => {
          if (cancelled) return;
          const nextRun = response.run || null;
          setCompetitorBulkRun(nextRun);
          const nextStatus = normalizeText(nextRun?.status);
          if (nextStatus && !["queued", "running"].includes(nextStatus)) {
            window.clearInterval(timer);
            setCompetitorBulkRunning(false);
            setCompetitorBulkNotice(
              nextStatus === "completed"
                ? `Подбор завершен. Создано: ${Number(nextRun?.created_count || 0)}, обновлено: ${Number(nextRun?.updated_count || 0)}.`
                : `Подбор остановлен со статусом: ${nextStatus}.`,
            );
            setReloadVersion((value) => value + 1);
          }
        })
        .catch(() => {
          if (!cancelled) {
            setCompetitorBulkNotice("Не удалось обновить статус подбора. Обновите страницу или повторите позже.");
          }
        });
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [competitorBulkRun?.id, competitorBulkRun?.status]);

  function handleSectionSelect(id: SectionId) {
    setActiveSection(id);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (id === "overview") {
        next.delete("tab");
      } else if (id === "competitors") {
        next.set("tab", "sources");
      } else {
        next.set("tab", id);
      }
      return next;
    }, { replace: true });
  }

  function handleOpenFeature(feature: ProductFeatureValue) {
    const index = features.indexOf(feature);
    setSelectedFeatureKey(featureKey(feature, index >= 0 ? index : 0));
    handleSectionSelect("attributes");
  }

  function toggleCompetitorSelection(id: string) {
    const normalized = normalizeText(id);
    if (!normalized) return;
    setCompetitorSelectedIds((prev) => {
      if (prev.includes(normalized)) return prev.filter((item) => item !== normalized);
      return [...prev, normalized];
    });
  }

  function toggleVisibleCompetitorSelection() {
    setCompetitorSelectedIds((prev) => {
      const visible = new Set(filteredCompetitorIds);
      if (!visible.size) return prev;
      if (allVisibleCompetitorsSelected) return prev.filter((id) => !visible.has(id));
      const next = new Set(prev);
      for (const id of filteredCompetitorIds) next.add(id);
      return Array.from(next);
    });
  }

  async function handleRunCompetitorDiscoveryForSelected() {
    const ids = selectedVisibleCompetitorIds;
    if (!ids.length || competitorBulkRunning) return;
    setCompetitorBulkRunning(true);
    setCompetitorBulkNotice("");
    setCompetitorBulkRun(null);
    try {
      const response = await api<CompetitorDiscoveryRunResp>("/competitor-mapping/discovery/run", {
        method: "POST",
        body: JSON.stringify({
          background: true,
          product_ids: ids,
          sources: ["restore", "store77"],
          limit: ids.length,
          use_ai: true,
        }),
      });
      const status = normalizeText(response.run?.status) || "queued";
      setCompetitorBulkRun(response.run || { status });
      setCompetitorBulkNotice(`Запущен подбор по ${ids.length} выбранным SKU. Статус: ${status}.`);
      if (!["queued", "running"].includes(status)) {
        setCompetitorBulkRunning(false);
        setReloadVersion((value) => value + 1);
      }
    } catch (err) {
      setCompetitorBulkNotice(err instanceof Error ? err.message : "Не удалось запустить подбор по SKU.");
      setCompetitorBulkRunning(false);
    }
  }

  async function handleConfirmSafeCompetitorsForSelected() {
    const ids = selectedVisibleCompetitorIds;
    if (!ids.length || competitorBulkConfirming) return;
    setCompetitorBulkConfirming(true);
    setCompetitorBulkNotice("");
    try {
      const response = await api<CompetitorSafeConfirmResp>("/competitor-mapping/discovery/product-candidates/confirm-safe", {
        method: "POST",
        body: JSON.stringify({
          product_ids: ids,
          sources: ["restore", "store77"],
          min_score: 0.9,
        }),
      });
      const confirmed = Number(response.confirmed_count || 0);
      const skipped = response.skipped?.length || 0;
      setCompetitorBulkNotice(
        confirmed
          ? `Подтверждено точных ссылок: ${confirmed}. Пропущено: ${skipped}. Теперь можно загрузить параметры и медиа.`
          : `Точных кандидатов для автоподтверждения нет. Пропущено: ${skipped}. Откройте SKU и проверьте кандидатов вручную.`,
      );
      setReloadVersion((value) => value + 1);
    } catch (err) {
      setCompetitorBulkNotice(err instanceof Error ? err.message : "Не удалось подтвердить точные кандидаты.");
    } finally {
      setCompetitorBulkConfirming(false);
    }
  }

  async function handleEnrichConfirmedCompetitorsForSelected() {
    const ids = selectedVisibleCompetitorIds;
    if (!ids.length || competitorBulkEnriching) return;
    setCompetitorBulkEnriching(true);
    setCompetitorBulkNotice("");
    try {
      const response = await api<CompetitorEnrichBatchResp>("/competitor-mapping/discovery/product-enrich/jobs/batch", {
        method: "POST",
        body: JSON.stringify({
          product_ids: ids,
          limit: ids.length,
        }),
      });
      const queued = Number(response.queued_count || 0);
      const skipped = response.skipped?.length || 0;
      setCompetitorBulkNotice(
        queued
          ? `Запущена загрузка параметров и медиа для ${queued} SKU. Без подтвержденных ссылок: ${skipped}.`
          : `Нет SKU с подтвержденными ссылками для загрузки. Пропущено: ${skipped}.`,
      );
      setReloadVersion((value) => value + 1);
    } catch (err) {
      setCompetitorBulkNotice(err instanceof Error ? err.message : "Не удалось запустить загрузку медиа по выбранным SKU.");
    } finally {
      setCompetitorBulkEnriching(false);
    }
  }

  if (loading) {
    return <ProductWorkspaceSkeleton />;
  }

  if (error) {
    return (
      <div className="page-shell">
        <Alert tone="error">{error}</Alert>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="page-shell">
        <EmptyState title="Товар не найден" description="Проверь идентификатор товара и попробуй снова." />
      </div>
    );
  }

  return (
    <div className="page-shell productWorkspacePage">
      <div className="productWorkspaceTopbar productWorkspaceCompactTopbar">
        <div className="productWorkspaceTopbarMain">
          <div className="productWorkspaceEyebrow">Карточка товара</div>
          <div className="productWorkspaceHeadingRow">
            <h1>{normalizeText(product.sku_gt) || normalizeText(product.sku_pim) || product.id}</h1>
            <Badge tone={toneForStatus(normalizeText(product.status))}>{normalizeText(product.status) || "draft"}</Badge>
          </div>
          <div className="productWorkspaceMetaRow">
            <span>{product.title}</span>
            <span>{categoryPath || "Категория не задана"}</span>
          </div>
        </div>
        <div className="productWorkspaceTopbarActions">
          <Button variant="primary">Сохранить</Button>
          <Button variant="danger" onClick={deleteProduct}>Удалить</Button>
          <Link className="btn" to="/products">
            К очереди товаров
          </Link>
        </div>
      </div>

      {justCreated ? (
        <Card className="productWorkspaceCreatedGuide">
          <div>
            <strong>SKU создан. Следующий шаг — подтвердить источники.</strong>
            <span>Для группы вариантов выберите нужные SKU, запустите поиск re-store/store77 и загрузите параметры, описание и медиа только из подтвержденных ссылок.</span>
          </div>
          <Button variant="primary" onClick={() => handleSectionSelect("competitors")}>Открыть источники</Button>
        </Card>
      ) : null}

      {nextAction ? (
        <Card className="productWorkspaceNextAction">
          <div className="productWorkspaceNextActionText">
            <Badge tone={nextAction.tone}>{nextAction.title}</Badge>
            <span>{nextAction.detail}</span>
          </div>
          {nextAction.href ? (
            <Link className="btn primary" to={nextAction.href}>{nextAction.cta}</Link>
          ) : nextAction.tab ? (
            <Button variant="primary" onClick={() => handleSectionSelect(nextAction.tab as SectionId)}>{nextAction.cta}</Button>
          ) : null}
        </Card>
      ) : null}

      <Card className="productWorkspaceLineageCard">
        <div className="productWorkspaceLineageHead">
          <div>
            <strong>Почему карточка заполнена</strong>
            <span>Видно, какие данные уже есть в PIM, откуда пришли значения и что выбрано для экспорта.</span>
          </div>
          <Link className="btn" to={productExportHref(product.id)}>
            Проверить payload
          </Link>
        </div>
        <div className="productWorkspaceLineageGrid">
          <button type="button" onClick={() => handleSectionSelect("attributes")}>
            <span>Параметры PIM</span>
            <strong>{lineageSummary.filledFeatures}/{lineageSummary.totalFeatures || 0}</strong>
            <em>{lineageSummary.sourceRows ? `с источниками: ${lineageSummary.sourceRows}` : "источники не подтверждены"}</em>
          </button>
          <button type="button" onClick={() => handleSectionSelect("competitors")}>
            <span>Источники</span>
            <strong>{lineageSummary.sourceLabels.length || lineageSummary.mediaSources.length}</strong>
            <em>
              {[...lineageSummary.sourceLabels, ...lineageSummary.mediaSources.map(([label]) => label)].slice(0, 3).join(" · ") || "нет данных"}
            </em>
          </button>
          <button type="button" onClick={() => handleSectionSelect("media")}>
            <span>Медиа</span>
            <strong>{lineageSummary.exportMedia}/{lineageSummary.mediaTotal}</strong>
            <em>выбрано для выгрузки</em>
          </button>
          <Link to={productExportHref(product.id)}>
            <span>Площадки</span>
            <strong>{lineageSummary.activeMarketplaces}/{lineageSummary.marketplacesTotal || 0}</strong>
            <em>активные карточки/каналы</em>
          </Link>
        </div>
      </Card>

      <WorkspaceFrame
        className="productWorkspaceLayout"
        sidebar={
          <ProductWorkspaceSectionNav
            activeSection={activeSection}
            onSelect={handleSectionSelect}
            productId={product.id}
          />
        }
        main={
          <div className="productWorkspaceMainStack productCockpitStack">
            {activeSection === "overview" ? (
              <>
                <ProductCommerceHero
                  product={product}
                  categoryPath={categoryPath}
                  features={features}
                  media={media}
                  variants={variants}
                  channels={channels}
                  analogs={analogs}
                  accessories={accessories}
                />
                <div className="productWorkspaceTextBlock productCockpitDescription">
                  <div className="productWorkspaceTextHead">
                    <div className="productWorkspaceTextLabel">Описание товара</div>
                    <Badge tone={descriptionSources.length ? "active" : "pending"}>
                      {descriptionSources.length ? `${descriptionSources.length} источ.` : "нет источника"}
                    </Badge>
                  </div>
                  <div
                    className="productWorkspaceRichText"
                    dangerouslySetInnerHTML={{
                      __html: normalizeText(product.content?.description) || "<p>Описание пока не заполнено.</p>",
                    }}
                  />
                  {descriptionSources.length ? (
                    <div className="productDescriptionEvidence">
                      {descriptionSources.slice(0, 3).map((entry) => (
                        <article key={`${entry.provider}:${entry.detail}`} className="productSourceEvidence">
                          <div>
                            <strong>{entry.label}</strong>
                            <span>{entry.provider}</span>
                          </div>
                          <dl>
                            <div><dt>Источник</dt><dd title={entry.detail}>{compactText(entry.detail, 120)}</dd></div>
                            <div><dt>Фрагмент</dt><dd title={entry.value || undefined}>{entry.value ? compactText(entry.value, 160) : "описание сохранено без фрагмента"}</dd></div>
                            <div><dt>Обновлено</dt><dd>{entry.updatedAt ? new Date(entry.updatedAt).toLocaleString("ru-RU") : "—"}</dd></div>
                          </dl>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="productDescriptionEvidenceEmpty">
                      Источник описания не зафиксирован. Проверьте импорт площадки или подтвержденные карточки конкурентов перед финальной отправкой.
                    </div>
                  )}
                </div>
              </>
            ) : null}

            {activeSection === "attributes" ? (
              <Card title="Параметры и значения">
                <ProductAttributeWorkbench
                  features={features}
                  variants={variants}
                  hasInfoModel={hasInfoModel}
                  rawFeatureCount={rawFeatures.length}
                  channels={channels}
                  parameterFlow={parameterFlow}
                  productId={product.id}
                  categoryId={product.category_id}
                  selectedKey={selectedFeatureKey}
                  onSelect={setSelectedFeatureKey}
                  onSaveFeatureValue={saveFeatureValue}
                  onSaveFeatureValues={saveFeatureValues}
                  savingFeatureKey={featureSavingKey}
                  saveNotice={featureNotice}
                />
              </Card>
            ) : null}

            {activeSection === "sources" ? (
              <Card title="Трассировка источников">
                <ProductSourcesWorkbench features={features} categoryId={product.category_id} />
              </Card>
            ) : null}

            {activeSection === "channels" ? (
              <Card title="Площадки и экспортные значения">
                {channels ? (
                  <div className="productWorkspaceChannelGrid">
                    {channels.marketplaces.map((channel) => (
                      <article key={channel.title} className="productWorkspaceChannelCard">
                        <div className="productWorkspaceChannelHead">
                          <strong>{channel.title}</strong>
                          <Badge tone={toneForStatus(channel.status)}>{channel.status}</Badge>
                        </div>
                        <div className="productWorkspaceChannelMeta">
                          <span>Рейтинг контента: {channel.content_rating || "Нет данных"}</span>
                          <span>Магазины: {channel.stores_count || 0}</span>
                        </div>
                      </article>
                    ))}
                    {channels.external_systems.map((channel) => (
                      <article key={channel.title} className="productWorkspaceChannelCard">
                        <div className="productWorkspaceChannelHead">
                          <strong>{channel.title}</strong>
                          <Badge tone={toneForStatus(channel.status)}>{channel.status}</Badge>
                        </div>
                      </article>
                    ))}
                    {channels.competitors.map((channel) => (
                      <article key={channel.key} className="productWorkspaceChannelCard">
                        <div className="productWorkspaceChannelHead">
                          <strong>{channel.title}</strong>
                          <Badge tone={toneForStatus(channel.status)}>{channel.status}</Badge>
                        </div>
                        <div className="productWorkspaceChannelMeta">
                          <span>{normalizeText(channel.url) || "URL не задан"}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : channelsLoading ? (
                  <EmptyState title="Загружаем channel summary" description="Сводка по каналам еще собирается." />
                ) : (
                  <EmptyState title="Канальные статусы временно недоступны" description="Базовый товар уже загружен, но summary endpoint не вернул данные." />
                )}
              </Card>
            ) : null}

            {activeSection === "competitors" ? (
              <div className="pn-competitorGroupWorkspace">
                {competitorGroupItems.length > 1 ? (
                  <div className="pn-card pn-competitorGroupCard">
                    <div className="pn-cardTitle">Подбор конкурентов по SKU группы</div>
                    <div className="pn-muted pn-competitorGroupLead">
                      Выберите SKU, затем запускайте поиск re-store/store77, подтверждайте кандидата или добавляйте точную ссылку вручную.
                      Насыщение параметров и медиа применяется только к выбранному SKU.
                    </div>
                    <div className="pn-competitorSkuToolbar">
                      <input
                        className="pn-competitorSkuSearch"
                        value={competitorSkuQuery}
                        onChange={(event) => setCompetitorSkuQuery(event.target.value)}
                        placeholder="Найти SKU, память, цвет, SIM..."
                      />
                      {[
                        ["all", "Все", competitorSkuStatusCounts.all],
                        ["neutral", "Не сканировали", competitorSkuStatusCounts.neutral],
                        ["pending", "Кандидаты", competitorSkuStatusCounts.pending],
                        ["active", "Подтверждено", competitorSkuStatusCounts.active],
                        ["danger", "Проблемы", competitorSkuStatusCounts.danger],
                      ].map(([key, label, count]) => (
                        <button
                          key={String(key)}
                          type="button"
                          className={`pn-competitorSkuFilter${competitorSkuFilter === key ? " isActive" : ""}`}
                          onClick={() => setCompetitorSkuFilter(key as "all" | CompetitorSkuStatus["tone"])}
                        >
                          {label} <strong>{count}</strong>
                        </button>
                      ))}
                      <button
                        type="button"
                        className="pn-competitorSkuRun"
                        onClick={handleRunCompetitorDiscoveryForSelected}
                        disabled={competitorBulkRunning || competitorBulkConfirming || competitorBulkEnriching || !selectedVisibleCompetitorIds.length}
                      >
                        {competitorBulkRunning ? "Подбор идет..." : `Найти выбранные ${selectedVisibleCompetitorIds.length}`}
                      </button>
                      <button
                        type="button"
                        className="pn-competitorSkuRun"
                        onClick={handleConfirmSafeCompetitorsForSelected}
                        disabled={competitorBulkRunning || competitorBulkConfirming || competitorBulkEnriching || !selectedVisibleCompetitorIds.length}
                      >
                        {competitorBulkConfirming ? "Подтверждаю..." : "Подтвердить точные"}
                      </button>
                      <button
                        type="button"
                        className="pn-competitorSkuRun"
                        onClick={handleEnrichConfirmedCompetitorsForSelected}
                        disabled={competitorBulkRunning || competitorBulkConfirming || competitorBulkEnriching || !selectedVisibleCompetitorIds.length}
                      >
                        {competitorBulkEnriching ? "Ставлю в очередь..." : "Загрузить медиа"}
                      </button>
                    </div>
                    <div className="pn-competitorSkuBulkBar">
                      <button type="button" className="pn-competitorSkuSelectAll" onClick={toggleVisibleCompetitorSelection} disabled={!filteredCompetitorIds.length}>
                        {allVisibleCompetitorsSelected ? "Снять выбор с видимых" : `Выбрать видимые ${filteredCompetitorIds.length}`}
                      </button>
                      <span>
                        Выбрано {selectedVisibleCompetitorIds.length} из {filteredCompetitorIds.length} видимых SKU. Подбор запускается только по выбранным строкам.
                      </span>
                    </div>
                    {competitorBulkNotice || competitorBulkRun ? (
                      <div className="pn-competitorSkuNotice">
                        <strong>{competitorBulkNotice || "Подбор конкурентов запущен."}</strong>
                        {competitorBulkRun ? (
                          <span>
                            Run: {normalizeText(competitorBulkRun.id) || "—"} · статус {normalizeText(competitorBulkRun.status) || "queued"} · обработано {Number(competitorBulkRun.scanned_products_count || 0)}
                          </span>
                        ) : null}
                      </div>
                    ) : null}
                    <div className="pn-competitorSkuTable">
                      <div className="pn-competitorSkuRow pn-competitorSkuHead">
                        <span>
                          <input
                            type="checkbox"
                            checked={allVisibleCompetitorsSelected}
                            onChange={toggleVisibleCompetitorSelection}
                            aria-label="Выбрать все видимые SKU"
                          />
                        </span>
                        <span>SKU GT</span>
                        <span>Товар</span>
                        <span>Статус</span>
                        <span>Действие</span>
                      </div>
                      {filteredCompetitorGroupItems.map((item) => {
                        const isActive = item.id === selectedCompetitorItem?.id;
                        const skuStatus = competitorSkuStatuses[item.id] || { label: "не сканировали", detail: "источники еще не проверялись", tone: "neutral" as const, sources: [] };
                        const itemId = normalizeText(item.id);
                        const isSelected = selectedCompetitorSet.has(itemId);
                        const actionLabel = isActive
                          ? "Текущий SKU"
                          : skuStatus.tone === "pending"
                            ? "Разобрать"
                            : skuStatus.tone === "active"
                              ? "Проверить"
                              : skuStatus.tone === "danger"
                                ? "Исправить"
                                : "Выбрать";
                        return (
                          <div
                            key={item.id}
                            className={`pn-competitorSkuRow${isActive ? " isActive" : ""}`}
                          >
                            <span>
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => toggleCompetitorSelection(itemId)}
                                aria-label={`Выбрать SKU ${normalizeText(item.sku_gt) || itemId}`}
                              />
                            </span>
                            <span className="pn-competitorSkuCode">{normalizeText(item.sku_gt) || normalizeText(item.sku_pim) || "—"}</span>
                            <span className="pn-competitorSkuTitle">
                              <strong>{normalizeText(item.title) || item.id}</strong>
                            </span>
                            <span className={`pn-competitorSkuReadiness is-${skuStatus.tone}`}>
                              <strong>{skuStatus.label}</strong>
                              {skuStatus.sources?.length ? (
                                <span className="pn-competitorSourceChips">
                                  {skuStatus.sources.map((source) => (
                                    <em key={`${item.id}-${source.id}`} className={`is-${source.tone}`}>{source.label}</em>
                                  ))}
                                </span>
                              ) : (
                                <em>{skuStatus.detail}</em>
                              )}
                            </span>
                            <button type="button" className="pn-competitorSkuAction" onClick={() => setCompetitorProductId(item.id)}>
                              {actionLabel}
                            </button>
                          </div>
                        );
                      })}
                      {!filteredCompetitorGroupItems.length ? (
                        <div className="pn-competitorSkuEmpty">По этому фильтру SKU не найдены.</div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
                <ProductCompetitorPanel
                  productId={selectedCompetitorItem?.id || product.id}
                  onEnriched={() => setReloadVersion((value) => value + 1)}
                />
              </div>
            ) : null}

            {activeSection === "media" ? (
              <Card title="Медиа">
                {media.length ? (
                  <>
                    <div className="productWorkspaceMediaHint">
                      <span>В экспорт уйдут только отмеченные изображения, в порядке слева направо.</span>
                      <div className="productWorkspaceMediaHintActions">
                        {selectedReviewMediaCount ? (
                          <Button
                            className="productWorkspaceMediaReviewButton"
                            disabled={mediaSaving}
                            onClick={excludeReviewMediaFromExport}
                          >
                            Не выгружать на проверке
                          </Button>
                        ) : null}
                        <strong>{selectedMediaCount}/{media.length}</strong>
                      </div>
                    </div>
                    {mediaNotice ? <Alert tone={mediaNotice.includes("Не удалось") ? "error" : "success"}>{mediaNotice}</Alert> : null}
                    <div className="productWorkspaceMediaGrid">
                      {media.map((item, index) => (
                        <article key={item.url} className={`productWorkspaceMediaCard${item.selected === false ? " isDisabled" : ""}`}>
                          <img src={toRenderableMediaUrl(item.url)} alt={item.caption || product.title} loading="lazy" />
                          <div className="productWorkspaceMediaMeta">
                            <strong>{item.caption || `Фото ${index + 1}`}</strong>
                            <span>{mediaSourceTitle(item)} · {mediaShortName(item.url)}</span>
                            <span>{item.selected === false ? "Не выгружать" : `Экспорт #${item.export_order ?? index + 1}`}</span>
                            {isMediaWaitingForReview(item) ? (
                              <em>Нужна проверка перед выгрузкой</em>
                            ) : null}
                          </div>
                          <div className="productWorkspaceMediaActions">
                            <label className="productWorkspaceMediaToggle">
                              <input
                                type="checkbox"
                                checked={item.selected !== false}
                                disabled={mediaSaving}
                                onChange={(event) => toggleMediaForExport(index, event.target.checked)}
                              />
                              <span>Выгружать</span>
                            </label>
                            <div className="productWorkspaceMediaOrder" aria-label="Порядок выгрузки">
                              <Button className="productWorkspaceMediaOrderButton" disabled={mediaSaving || index === 0} onClick={() => moveMediaForExport(index, -1)}>Выше</Button>
                              <Button className="productWorkspaceMediaOrderButton" disabled={mediaSaving || index === media.length - 1} onClick={() => moveMediaForExport(index, 1)}>Ниже</Button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  </>
                ) : (
                  <EmptyState
                    title="Медиа блокирует выгрузку"
                    description="У SKU нет изображений в S3. Сначала подтверди карточку конкурента или добавь точную ссылку, затем загрузи параметры и медиа в карточку товара."
                    action={(
                      <div className="productWorkspaceEmptyActions">
                        <Button variant="primary" onClick={() => handleSectionSelect("competitors")}>
                          Найти карточки и загрузить медиа
                        </Button>
                        <Button onClick={() => handleSectionSelect("validation")}>
                          Проверить остальные блокеры
                        </Button>
                      </div>
                    )}
                  />
                )}
              </Card>
            ) : null}

            {activeSection === "validation" ? (
              <Card title="Валидация перед экспортом">
                <ProductValidationWorkbench
                  features={features}
                  media={media}
                  description={normalizeText(product.content?.description)}
                  exportHref={productExportHref(product.id)}
                  onOpenFeature={handleOpenFeature}
                  onOpenMedia={() => handleSectionSelect("media")}
                  onOpenCompetitors={() => handleSectionSelect("competitors")}
                />
              </Card>
            ) : null}

            {activeSection === "relations" ? (
              <Card title="Связи товара">
                <div className="productWorkspaceRelationsSplit">
                  <div>
                    <div className="productWorkspaceMiniTitle">Аналоги</div>
                    {analogs.length ? (
                      <ul className="productWorkspaceSimpleList">
                        {analogs.map((item, index) => (
                          <li key={`${item.id || item.sku || item.sku_gt || "analog"}-${index}`}>
                            <strong>{normalizeText(item.name) || "Без названия"}</strong>
                            <span>{normalizeText(item.sku_gt || item.sku) || "SKU не задан"}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="productWorkspaceEmptyNote">Аналоги не заданы.</div>
                    )}
                  </div>
                  <div>
                    <div className="productWorkspaceMiniTitle">Сопутствующие</div>
                    {accessories.length ? (
                      <ul className="productWorkspaceSimpleList">
                        {accessories.map((item, index) => (
                          <li key={`${item.id || item.sku || item.sku_gt || "related"}-${index}`}>
                            <strong>{normalizeText(item.name) || "Без названия"}</strong>
                            <span>{normalizeText(item.sku_gt || item.sku) || "SKU не задан"}</span>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="productWorkspaceEmptyNote">Связанные товары не заданы.</div>
                    )}
                  </div>
                </div>
              </Card>
            ) : null}

            {activeSection === "variants" ? (
              <Card title="Варианты SKU">
                {variants.length ? (
                  <div className="productWorkspaceTableWrap">
                    <table className="productWorkspaceTable">
                      <thead>
                        <tr>
                          <th>Товар</th>
                          <th>SKU GT</th>
                          <th>SKU PIM</th>
                          <th>Статус</th>
                        </tr>
                      </thead>
                      <tbody>
                        {variants.map((variant) => (
                          <tr key={variant.id}>
                            <td>
                              <Link to={`/products/${variant.id}`}>{normalizeText(variant.title) || variant.id}</Link>
                            </td>
                            <td>{normalizeText(variant.sku_gt) || "—"}</td>
                            <td>{normalizeText(variant.sku_pim) || "—"}</td>
                            <td>{normalizeText(variant.status) || "draft"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title="Вариантов нет" description="SKU не входит в variant-family или другие SKU не добавлены." />
                )}
              </Card>
            ) : null}

            {activeSection === "create-flow" ? (
              <Card title="Новый процесс создания товара">
                <ProductCreateFlowPreview />
                <div className="productCockpitNextNote">
                  Следующий slice: заменить текущую страницу создания товара на wizard с этими шагами и автоматическим переходом в cockpit после создания SKU.
                </div>
              </Card>
            ) : null}
          </div>
        }
        inspector={
          <ProductWorkspaceInspector
            product={product}
            categoryPath={categoryPath}
            features={features}
            variants={variants}
            channels={channels}
            media={media}
          />
        }
      />
    </div>
  );
}

export default ProductWorkspaceFeature;
