import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
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
  source_values?: Record<string, unknown>;
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
};

type ProductContent = {
  description?: string;
  features?: ProductFeatureValue[];
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
};

type ProductResponse = {
  product: ProductData;
  variants?: VariantData[];
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
  { id: "overview", label: "Сводка", meta: "контекст SKU" },
  { id: "attributes", label: "Параметры", meta: "значения и источники" },
  { id: "sources", label: "Источники", meta: "импорт, excel, конкуренты" },
  { id: "channels", label: "Площадки", meta: "вывод и альтернативы" },
  { id: "competitors", label: "Конкуренты", meta: "links review" },
  { id: "media", label: "Медиа", meta: "S3 assets" },
  { id: "validation", label: "Валидация", meta: "ошибки перед экспортом" },
  { id: "relations", label: "Связи", meta: "аналоги и комплекты" },
  { id: "variants", label: "Варианты", meta: "SKU family" },
  { id: "create-flow", label: "Создание", meta: "новый процесс" },
];

function normalizeText(value: unknown): string {
  return String(value ?? "").trim();
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
      out.push({ url, caption: normalizeText(item?.caption) || undefined });
    }
  }
  return out;
}

function featureValue(feature: ProductFeatureValue): string {
  const value = normalizeText(feature.value);
  if (value) return value;
  const values = Array.isArray(feature.values) ? feature.values.map((item) => normalizeText(item)).filter(Boolean) : [];
  return values.join(", ");
}

function featureKey(feature: ProductFeatureValue, index: number): string {
  return normalizeText(feature.code) || normalizeText(feature.name) || `feature-${index}`;
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

function normalizeForMarketplace(provider: string, value: string): string {
  const normalized = normalizeText(value);
  if (!normalized) return "Не заполнено";
  const lower = normalized.toLowerCase();
  const memoryMatch = lower.match(/(\d+)\s*(гб|gb|тб|tb)/i);
  if (memoryMatch) {
    const amount = memoryMatch[1];
    const unit = memoryMatch[2].toLowerCase();
    const isTb = unit === "тб" || unit === "tb";
    if (provider.includes("ozon")) return `${amount}${isTb ? "TB" : "GB"}`;
    if (provider.includes("wildberries")) return amount;
    return `${amount} ${isTb ? "ТБ" : "ГБ"}`;
  }
  if (provider.includes("ozon")) return normalized.replace(/\s+/g, " ");
  return normalized;
}

function marketplaceProjections(value: string, channels: ChannelsSummary | null) {
  const providers = channels?.marketplaces.length
    ? channels.marketplaces.map((item) => item.title)
    : ["Яндекс Маркет", "Ozon", "Wildberries"];
  return providers.map((provider) => ({
    provider,
    value: normalizeForMarketplace(provider.toLowerCase(), value),
    status: value ? "готово" : "нет значения",
  }));
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

function toneForStatus(status: string): "active" | "pending" | "danger" | "neutral" {
  const value = normalizeText(status).toLowerCase();
  if (!value) return "neutral";
  if (value.includes("ok") || value.includes("готов") || value.includes("active") || value.includes("опублик")) return "active";
  if (value.includes("ошиб") || value.includes("error") || value.includes("расхожд")) return "danger";
  if (value.includes("draft") || value.includes("чернов") || value.includes("pending") || value.includes("модерац")) return "pending";
  return "neutral";
}

function ProductWorkspaceSectionNav({
  activeSection,
  onSelect,
}: {
  activeSection: SectionId;
  onSelect: (id: SectionId) => void;
}) {
  return (
    <nav className="productWorkspaceNav" aria-label="Навигация по товару">
      <div className="productWorkspaceNavTitle">Workflow товара</div>
      <div className="productWorkspaceNavList">
        {SECTION_LABELS.map((section) => (
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
      </div>
    </nav>
  );
}

function ProductWorkflowStrip({
  activeSection,
  onSelect,
}: {
  activeSection: SectionId;
  onSelect: (id: SectionId) => void;
}) {
  return (
    <div className="productWorkflowStrip" aria-label="Product workflow">
      {SECTION_LABELS.slice(0, 7).map((section, index) => (
        <button
          key={section.id}
          type="button"
          className={`productWorkflowStep${activeSection === section.id ? " isActive" : ""}`}
          onClick={() => onSelect(section.id)}
        >
          <span>{String(index + 1).padStart(2, "0")}</span>
          <strong>{section.label}</strong>
        </button>
      ))}
    </div>
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
      <InspectorPanel title="Сводка" subtitle="Ключевой контекст товара">
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
  channels,
  selectedKey,
  onSelect,
}: {
  features: ProductFeatureValue[];
  channels: ChannelsSummary | null;
  selectedKey: string;
  onSelect: (key: string) => void;
}) {
  const selectedFeature = useMemo(() => {
    return features.find((feature, index) => featureKey(feature, index) === selectedKey) || features[0] || null;
  }, [features, selectedKey]);
  const selectedValue = selectedFeature ? featureValue(selectedFeature) : "";
  const sourceEntries = selectedFeature ? sourceEntriesForFeature(selectedFeature) : [];
  const projections = marketplaceProjections(selectedValue, channels);
  const filledCount = features.filter((feature) => featureValue(feature)).length;
  const conflictCount = features.filter((feature) => {
    const entries = sourceEntriesForFeature(feature);
    const values = new Set(entries.map((item) => item.canonical || item.resolved || item.raw).filter(Boolean).map((item) => item.toLowerCase()));
    return values.size > 1;
  }).length;

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
                  <em>{value || "Не заполнено"}</em>
                </span>
                <Badge tone={qualityTone(!!value)}>{sourceCount ? `${sourceCount} источн.` : "ручн."}</Badge>
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
                <p>{normalizeText(selectedFeature.code) || "код параметра не задан"}</p>
              </div>
              <div className="productCanonicalValue">
                <span>Значение в PIM</span>
                <strong>{selectedValue || "Не заполнено"}</strong>
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
                          <div><dt>Raw</dt><dd>{entry.raw || "—"}</dd></div>
                          <div><dt>Resolved</dt><dd>{entry.resolved || "—"}</dd></div>
                          <div><dt>Canonical</dt><dd>{entry.canonical || "—"}</dd></div>
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
                <div className="productMarketplaceProjectionList">
                  {projections.map((projection) => (
                    <article key={projection.provider} className="productMarketplaceProjection">
                      <div>
                        <strong>{projection.provider}</strong>
                        <span>{projection.status}</span>
                      </div>
                      <code>{projection.value}</code>
                    </article>
                  ))}
                </div>
              </div>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}

function ProductSourcesWorkbench({ features }: { features: ProductFeatureValue[] }) {
  const rows = features.flatMap((feature) =>
    sourceEntriesForFeature(feature).map((entry) => ({
      feature: normalizeText(feature.name) || normalizeText(feature.code) || "Параметр",
      code: normalizeText(feature.code),
      ...entry,
    })),
  );
  if (!rows.length) {
    return <EmptyState title="Источники пока не связаны" description="Когда товар заполнится из импорта, Excel, конкурентов или ручной проверки, здесь появится трассировка по каждому параметру." />;
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
  onSelectSection,
}: {
  product: ProductData;
  categoryPath: string;
  features: ProductFeatureValue[];
  media: ProductMedia[];
  variants: VariantData[];
  channels: ChannelsSummary | null;
  analogs: ProductRelation[];
  accessories: ProductRelation[];
  onSelectSection: (id: SectionId) => void;
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
                <span>Характеристики</span>
                <strong>Пока не заполнены</strong>
              </div>
            )}
          </div>

          <div className="productCommerceActions">
            <Button variant="primary" onClick={() => onSelectSection("attributes")}>Редактировать параметры</Button>
            <Button onClick={() => onSelectSection("media")}>Медиа</Button>
            <Button onClick={() => onSelectSection("channels")}>Площадки</Button>
            <Link className="btn" to="/products">К списку</Link>
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
          <div className="productCommerceNextSteps">
            <button type="button" onClick={() => onSelectSection("sources")}>Проверить источники</button>
            <button type="button" onClick={() => onSelectSection("validation")}>Открыть валидацию</button>
            <button type="button" onClick={() => onSelectSection("relations")}>Связи товара</button>
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
            <InspectorPanel title="Сводка" subtitle="Загрузка товара">
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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [product, setProduct] = useState<ProductData | null>(null);
  const [variants, setVariants] = useState<VariantData[]>([]);
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [channels, setChannels] = useState<ChannelsSummary | null>(null);
  const [channelsLoading, setChannelsLoading] = useState(false);
  const [activeSection, setActiveSection] = useState<SectionId>("overview");
  const [selectedFeatureKey, setSelectedFeatureKey] = useState("");
  const [reloadVersion, setReloadVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    let channelsAbort: AbortController | null = null;
    async function run() {
      setLoading(true);
      setError("");
      setProduct(null);
      setVariants([]);
      setNodes([]);
      setChannels(null);
      setChannelsLoading(false);
      let shellResolved = false;
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
            content: {},
          };
          setProduct(summaryProduct);
          setLoading(false);
          return summaryProduct;
        })
        .catch(() => {
          shellResolved = false;
          return null;
        });
      try {
        const productResponse = await api<ProductResponse>(`/products/${productId}`);
        if (cancelled) return;
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
        setProduct(mergedProduct);
        setVariants(Array.isArray(productResponse.variants) ? productResponse.variants : []);
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

  const features = useMemo(() => product?.content?.features || [], [product]);
  const media = useMemo(() => flattenMedia(product?.content), [product]);
  const categoryPath = useMemo(() => buildCategoryPath(nodes, product?.category_id), [nodes, product?.category_id]);

  const accessories = useMemo(() => {
    return (product?.content?.related || []).filter((item) => normalizeText(item.name) || normalizeText(item.sku) || normalizeText(item.sku_gt));
  }, [product]);

  const analogs = useMemo(() => {
    return (product?.content?.analogs || []).filter((item) => normalizeText(item.name) || normalizeText(item.sku) || normalizeText(item.sku_gt));
  }, [product]);

  const missingAttributes = useMemo(() => features.filter((feature) => !featureValue(feature)), [features]);

  useEffect(() => {
    if (!features.length) {
      setSelectedFeatureKey("");
      return;
    }
    setSelectedFeatureKey((prev) => {
      if (prev && features.some((feature, index) => featureKey(feature, index) === prev)) return prev;
      return featureKey(features[0], 0);
    });
  }, [features]);

  function handleSectionSelect(id: SectionId) {
    setActiveSection(id);
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
          <Link className="btn" to="/products">
            К очереди товаров
          </Link>
        </div>
      </div>

      <WorkspaceFrame
        className="productWorkspaceLayout"
        sidebar={
          <ProductWorkspaceSectionNav
            activeSection={activeSection}
            onSelect={handleSectionSelect}
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
                  onSelectSection={handleSectionSelect}
                />
                <ProductWorkflowStrip activeSection={activeSection} onSelect={handleSectionSelect} />
                <div className="productWorkspaceTextBlock productCockpitDescription">
                  <div className="productWorkspaceTextLabel">Описание товара</div>
                  <div
                    className="productWorkspaceRichText"
                    dangerouslySetInnerHTML={{
                      __html: normalizeText(product.content?.description) || "<p>Описание пока не заполнено.</p>",
                    }}
                  />
                </div>
              </>
            ) : null}

            {activeSection === "attributes" ? (
              <Card title="Параметры и значения">
                <ProductAttributeWorkbench
                  features={features}
                  channels={channels}
                  selectedKey={selectedFeatureKey}
                  onSelect={setSelectedFeatureKey}
                />
              </Card>
            ) : null}

            {activeSection === "sources" ? (
              <Card title="Трассировка источников">
                <ProductSourcesWorkbench features={features} />
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
              <ProductCompetitorPanel productId={product.id} onEnriched={() => setReloadVersion((value) => value + 1)} />
            ) : null}

            {activeSection === "media" ? (
              <Card title="Медиа">
                {media.length ? (
                  <div className="productWorkspaceMediaGrid">
                    {media.map((item) => (
                      <article key={item.url} className="productWorkspaceMediaCard">
                        <img src={toRenderableMediaUrl(item.url)} alt={item.caption || product.title} loading="lazy" />
                        <div className="productWorkspaceMediaMeta">
                          <strong>{item.caption || "Изображение товара"}</strong>
                          <span>{item.url}</span>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState title="Медиа пока не добавлены" description="На этом этапе у товара нет загруженных изображений из S3." />
                )}
              </Card>
            ) : null}

            {activeSection === "validation" ? (
              <Card title="Валидация перед экспортом">
                <div className="productWorkspaceValidationGrid">
                  <div className="productWorkspaceValidationCard">
                    <span>Пустые параметры</span>
                    <strong>{missingAttributes.length}</strong>
                  </div>
                  <div className="productWorkspaceValidationCard">
                    <span>Описание</span>
                    <strong>{normalizeText(product.content?.description) ? "Готово" : "Пусто"}</strong>
                  </div>
                  <div className="productWorkspaceValidationCard">
                    <span>Медиа</span>
                    <strong>{media.length ? "Готово" : "Пусто"}</strong>
                  </div>
                </div>
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
