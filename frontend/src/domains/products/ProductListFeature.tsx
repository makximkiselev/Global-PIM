import {
  startTransition,
  useDeferredValue,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useOrgPath } from "../../app/orgRoutes";
import Card from "../../components/ui/Card";
import Badge from "../../components/ui/Badge";
import Button from "../../components/ui/Button";
import Alert from "../../components/ui/Alert";
import EmptyState from "../../components/ui/EmptyState";
import DataToolbar from "../../components/data/DataToolbar";
import TextInput from "../../components/ui/TextInput";
import Select from "../../components/ui/Select";
import SideSheet from "../../components/ui/SideSheet";
import { api } from "../../lib/api";

type ProductItem = {
  id: string;
  title?: string;
  name?: string;
  category_id: string;
  category_path?: string;
  preview_url?: string;
  sku_pim?: string;
  sku_gt?: string;
  group_id?: string;
  group_name?: string;
  marketplace_statuses?: Record<string, { status?: string; present?: boolean }>;
  effective_template_id?: string;
  effective_template_name?: string;
  effective_template_source_category_id?: string;
};

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
  products_count?: number;
};

type GroupItem = {
  id: string;
  name: string;
};

type TemplateItem = {
  id: string;
  category_id?: string | null;
  name: string;
};

type ProductsPageDataResp = {
  ok?: boolean;
  products: ProductItem[];
  total: number;
  page: number;
  page_size: number;
  nodes: CatalogNode[];
  groups: GroupItem[];
  templates: TemplateItem[];
};

type CoreCatalogProductResp = {
  items: Array<{
    id: string;
    name?: string;
    title?: string;
    category_id?: string;
    sku_pim?: string;
    sku_gt?: string;
    group_id?: string;
    preview_url?: string;
    exports_enabled?: Record<string, unknown>;
  }>;
};

type QueueMode = "all" | "issues" | "no_template" | "no_ym" | "no_oz";

const DEFAULT_PAGE_SIZE = 50;
const RICH_PRODUCTS_TIMEOUT_MS = 3500;

function buildCategoryPath(nodeById: Map<string, CatalogNode>, categoryId: string): string {
  const target = String(categoryId || "").trim();
  if (!target) return "";
  const chain: string[] = [];
  const seen = new Set<string>();
  let current = nodeById.get(target);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    chain.push(current.name);
    current = current.parent_id ? nodeById.get(String(current.parent_id)) : undefined;
  }
  return chain.reverse().join(" / ");
}

function normalizeStatus(status?: string, present?: boolean): "good" | "warn" | "neutral" {
  const value = String(status || "").trim().toLowerCase();
  if (!present) return "neutral";
  if (!value) return "neutral";
  if (value.includes("ошибка") || value.includes("отклон") || value.includes("нет карточки")) return "warn";
  return "good";
}

function marketplaceLabel(provider: "yandex_market" | "ozon") {
  return provider === "yandex_market" ? "Я.Маркет" : "Ozon";
}

function marketplaceStatusMeta(product: ProductItem, provider: "yandex_market" | "ozon") {
  const raw = product.marketplace_statuses?.[provider] || {};
  const status = String(raw.status || "").trim();
  const present = !!raw.present;
  const tone = normalizeStatus(status, present);
  return {
    label: marketplaceLabel(provider),
    detail: present ? status || "есть" : "нет связи",
    tone,
  };
}

function compactCategoryPath(path?: string) {
  const parts = String(path || "")
    .split("/")
    .map((part) => part.trim())
    .filter(Boolean);
  if (!parts.length) return { primary: "Категория не определена", secondary: "" };
  return {
    primary: parts[parts.length - 1],
    secondary: parts.length > 1 ? parts.slice(0, -1).join(" / ") : "",
  };
}

function displayGroupName(product: ProductItem) {
  const name = String(product.group_name || "").trim();
  const id = String(product.group_id || "").trim();
  const visible = name && name !== id ? name : id;
  if (!visible) return { primary: "Без семейства", secondary: "" };
  const technical = visible.match(/^group[_-](\d+)$/i);
  if (technical) {
    return { primary: `Семейство SKU #${technical[1]}`, secondary: "варианты одной линейки" };
  }
  return { primary: visible, secondary: "варианты одной линейки" };
}

function queueModeLabel(mode: QueueMode): string {
  switch (mode) {
    case "issues":
      return "Проблемные";
    case "no_template":
      return "Без модели";
    case "no_ym":
      return "Без Я.Маркета";
    case "no_oz":
      return "Без Ozon";
    default:
      return "Все товары";
  }
}

function withCategoryHref(path: string, categoryId?: string | null, param = "category") {
  const id = String(categoryId || "").trim();
  return id ? `${path}?${param}=${encodeURIComponent(id)}` : path;
}

function catalogExchangeHref(tab: "import" | "export", categoryId?: string | null) {
  const params = new URLSearchParams({ tab });
  const id = String(categoryId || "").trim();
  if (id) params.set("category", id);
  return `/catalog/exchange?${params.toString()}`;
}

function withProductExportHref(productIds: string[]) {
  const ids = productIds.map((id) => String(id || "").trim()).filter(Boolean);
  const params = new URLSearchParams({ tab: "export" });
  if (!ids.length) return `/catalog/exchange?${params.toString()}`;
  const param = ids.length === 1 ? "product" : "products";
  params.set(param, ids.join(","));
  return `/catalog/exchange?${params.toString()}`;
}

function sourcesMappingHref(categoryId?: string | null, tab = "params", productId?: string | null) {
  const id = String(categoryId || "").trim();
  const params = new URLSearchParams({ tab });
  if (id) params.set("category", id);
  const product = String(productId || "").trim();
  if (product) params.set("product", product);
  return `/sources?${params.toString()}`;
}

function templateHref(product: ProductItem) {
  const sourceCategoryId = String(product.effective_template_source_category_id || product.category_id || "").trim();
  return sourcesMappingHref(sourceCategoryId, "sources", product.id);
}

function getProductNextStep(product: ProductItem): {
  title: string;
  detail: string;
  tone: "danger" | "pending" | "active";
  href: string;
  cta: string;
} {
  const hasTemplate = !!String(product.effective_template_name || "").trim();
  const ym = marketplaceStatusMeta(product, "yandex_market");
  const oz = marketplaceStatusMeta(product, "ozon");

  if (!hasTemplate) {
    return {
      title: "Нет модели категории",
      detail: "Сначала соберите параметры категории",
      tone: "danger",
      href: templateHref(product),
      cta: "Собрать модель",
    };
  }

  if (ym.tone !== "good" || oz.tone !== "good") {
    const missing = [ym, oz]
      .filter((item) => item.tone !== "good")
      .map((item) => item.label)
      .join(", ");
    return {
      title: "Проверить площадки",
      detail: missing ? `Не готово: ${missing}` : "Есть незакрытые связи",
      tone: "pending",
      href: sourcesMappingHref(product.category_id, "sources", product.id),
      cta: "Сопоставить",
    };
  }

  return {
    title: "Готов к выгрузке",
    detail: "Можно проверить экспорт SKU",
    tone: "active",
    href: withProductExportHref([product.id]),
    cta: "Экспорт",
  };
}

function ProductQueueSwitch({
  mode,
  onChange,
}: {
  mode: QueueMode;
  onChange: (next: QueueMode) => void;
}) {
  const items: Array<{ key: QueueMode; label: string }> = [
    { key: "all", label: "Все" },
    { key: "issues", label: "Проблемные" },
    { key: "no_template", label: "Без модели" },
    { key: "no_ym", label: "Без Я.Маркета" },
    { key: "no_oz", label: "Без Ozon" },
  ];

  return (
    <div className="productListQueueSwitch" role="tablist" aria-label="Режимы очереди товаров">
      {items.map((item) => (
        <button
          key={item.key}
          type="button"
          className={`productListQueueSwitchButton${mode === item.key ? " isActive" : ""}`}
          onClick={() => onChange(item.key)}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function ProductListEntryBar({
  total,
  visibleCount,
  queueMode,
  selectedCount,
  categoryId,
  categoryName,
  directCount,
}: {
  total: number;
  visibleCount: number;
  queueMode: QueueMode;
  selectedCount: number;
  categoryId?: string;
  categoryName?: string;
  directCount?: number;
}) {
  const orgPath = useOrgPath();
  const hasCategoryScope = Boolean(categoryId && categoryName);
  const branchLabel = hasCategoryScope ? `${total} SKU в выбранной ветке` : `${total} SKU в каталоге`;

  return (
    <div className="productListEntryBar">
      <div className="productListEntryTitleBlock">
        <div className="productListEntryEyebrow">Рабочая очередь</div>
        <h1>{hasCategoryScope ? `Товары: ${categoryName}` : "Товары"}</h1>
        <div className="productListEntryMeta">
          <span>{branchLabel}</span>
          {hasCategoryScope ? <span>{Math.max(0, Number(directCount || 0))} прямо здесь</span> : null}
          <span>{visibleCount} на экране</span>
          <span>{queueModeLabel(queueMode)}</span>
          {selectedCount ? <span>{selectedCount} выбрано</span> : null}
        </div>
      </div>
      <div className="productListEntryActions">
        <Link className="btn" to={orgPath("/catalog")}>
          Каталог
        </Link>
        <Link className="btn" to={orgPath(catalogExchangeHref("import", categoryId))}>
          Импорт
        </Link>
        <Link className="btn" to={orgPath(catalogExchangeHref("export", categoryId))}>
          Экспорт
        </Link>
        <Link className="btn primary" to={orgPath(withCategoryHref("/products/new", categoryId, "category_id"))}>
          Создать товар
        </Link>
      </div>
    </div>
  );
}

function ProductListSummaryStrip({
  rows,
  total,
  selectedCount,
  loading,
}: {
  rows: ProductItem[];
  total: number;
  selectedCount: number;
  loading: boolean;
}) {
  const noTemplate = rows.filter((product) => !String(product.effective_template_name || "").trim()).length;
  const ready = rows.filter((product) => {
    const hasTemplate = !!String(product.effective_template_name || "").trim();
    const ym = normalizeStatus(
      product.marketplace_statuses?.yandex_market?.status,
      product.marketplace_statuses?.yandex_market?.present,
    );
    const oz = normalizeStatus(
      product.marketplace_statuses?.ozon?.status,
      product.marketplace_statuses?.ozon?.present,
    );
    return hasTemplate && ym === "good" && oz === "good";
  }).length;
  const needsWork = Math.max(0, rows.length - ready);
  const withoutChannels = rows.filter((product) => {
    const ym = normalizeStatus(
      product.marketplace_statuses?.yandex_market?.status,
      product.marketplace_statuses?.yandex_market?.present,
    );
    const oz = normalizeStatus(
      product.marketplace_statuses?.ozon?.status,
      product.marketplace_statuses?.ozon?.present,
    );
    return ym !== "good" || oz !== "good";
  }).length;

  const items = [
    { label: "Всего SKU", value: total, meta: loading ? "обновляется" : `${rows.length} на странице` },
    { label: "Требуют работы", value: needsWork, meta: "модель, каналы или экспорт" },
    { label: "Без модели категории", value: noTemplate, meta: "сначала сопоставить параметры" },
    { label: "Нет готовых каналов", value: withoutChannels, meta: "Я.Маркет / Ozon" },
    { label: "Готовы", value: ready, meta: "можно проверять экспорт" },
    { label: "Выбрано", value: selectedCount, meta: selectedCount ? "доступны массовые действия" : "выбор через чекбоксы" },
  ];

  return (
    <div className="productListSummaryStrip" aria-label="Сводка очереди товаров">
      {items.map((item) => (
        <div key={item.label} className="productListSummaryItem">
          <div className="productListSummaryValue">{item.value}</div>
          <div className="productListSummaryCopy">
            <div className="productListSummaryLabel">{item.label}</div>
            <div className="productListSummaryMeta">{item.meta}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function ProductReadinessBadge({ product }: { product: ProductItem }) {
  const hasTemplate = !!String(product.effective_template_name || "").trim();
  const ym = normalizeStatus(
    product.marketplace_statuses?.yandex_market?.status,
    product.marketplace_statuses?.yandex_market?.present,
  );
  const oz = normalizeStatus(
    product.marketplace_statuses?.ozon?.status,
    product.marketplace_statuses?.ozon?.present,
  );

  let label = "Требует внимания";
  let tone: "danger" | "pending" | "active" = "danger";

  if (hasTemplate && ym === "good" && oz === "good") {
    label = "Готов";
    tone = "active";
  } else if (hasTemplate || ym === "good" || oz === "good") {
    label = "В работе";
    tone = "pending";
  }

  return <Badge tone={tone}>{label}</Badge>;
}

function ProductChannelsCell({ product }: { product: ProductItem }) {
  const channels = [
    marketplaceStatusMeta(product, "yandex_market"),
    marketplaceStatusMeta(product, "ozon"),
  ];

  return (
    <div className="productListChannels">
      {channels.map((channel) => {
        const compactLabel = channel.label === "Я.Маркет" ? "Маркет" : channel.label;
        return (
          <span
            key={channel.label}
            className={`productListChannelBadge productListChannelBadge--${channel.tone}`}
            title={`${channel.label}: ${channel.detail}`}
          >
            <span>{compactLabel}</span>
            <small>{channel.tone === "good" ? "ok" : "нет"}</small>
          </span>
        );
      })}
    </div>
  );
}

function ProductListInspector({
  product,
  selectedCount,
  onClearSelection,
  open,
  onClose,
}: {
  product: ProductItem | null;
  selectedCount: number;
  onClearSelection: () => void;
  open: boolean;
  onClose: () => void;
}) {
  const orgPath = useOrgPath();
  if (!product) {
    return null;
  }

  const title = String(product.title || product.name || "").trim() || product.id;
  const sku = String(product.sku_gt || "").trim() || "Без SKU";
  const group = String(product.group_name || "").trim();
  const templateName = String(product.effective_template_name || "").trim();
  const ymStatus = String(product.marketplace_statuses?.yandex_market?.status || "Нет данных");
  const ozStatus = String(product.marketplace_statuses?.ozon?.status || "Нет данных");
  const templateSourceCategoryId = String(product.effective_template_source_category_id || "").trim();

  return (
    <SideSheet
      open={open}
      onClose={onClose}
      eyebrow="Карточка SKU"
      title={sku}
      subtitle={title}
      className="productListInspectorOverlay"
    >
      <div className="productListInspectorStack">
        <div className="productListInspectorHero">
          <div className="productListInspectorTitle">{title}</div>
          <div className="productListInspectorCategory">{product.category_path || "Категория не определена"}</div>
        </div>

        <div className="productListInspectorSection">
          <div className="productListInspectorSectionTitle">Состояние</div>
          <div className="productListInspectorStatusRow">
            <ProductReadinessBadge product={product} />
            {group ? <Badge tone="neutral">Группа: {group}</Badge> : <Badge tone="neutral">Без группы</Badge>}
            {selectedCount > 1 ? <Badge tone="neutral">В выборе {selectedCount}</Badge> : null}
          </div>
          {selectedCount > 1 ? <Button onClick={onClearSelection}>Сбросить выбор</Button> : null}
        </div>

        <div className="productListInspectorSection">
          <div className="productListInspectorSectionTitle">Каналы</div>
          <div className="productListInspectorInfoList">
            <div className="productListInspectorInfoRow">
              <span>Я.Маркет</span>
              <strong>{ymStatus}</strong>
            </div>
            <div className="productListInspectorInfoRow">
              <span>Ozon</span>
              <strong>{ozStatus}</strong>
            </div>
          </div>
        </div>

        <div className="productListInspectorSection">
          <div className="productListInspectorSectionTitle">Модель</div>
          {templateName ? (
            <Link
              className="productListInlineLink"
              to={orgPath(templateSourceCategoryId ? `/templates/${encodeURIComponent(templateSourceCategoryId)}` : "/templates")}
            >
              {templateName}
            </Link>
          ) : (
            <div className="productListInspectorText">Модель не назначена. Такой SKU почти наверняка потребует ручной доводки.</div>
          )}
        </div>

        <div className="productListInspectorActions">
          <Link className="btn primary" to={orgPath(`/products/${encodeURIComponent(product.id)}`)}>
            Открыть SKU
          </Link>
          <Link className="btn" to={orgPath(sourcesMappingHref(product.category_id, "sources"))}>
            Открыть сопоставления
          </Link>
          <Link className="btn" to={orgPath(withProductExportHref([product.id]))}>
            Проверить этот SKU
          </Link>
        </div>
      </div>
    </SideSheet>
  );
}

type ProductListTableProps = {
  rows: ProductItem[];
  selectedIds: string[];
  selectedProductId: string | null;
  onToggleRow: (id: string, checked: boolean) => void;
  onSelectOnly: (id: string) => void;
  onToggleAll: (checked: boolean) => void;
  loading: boolean;
};

function ProductListTable({
  rows,
  selectedIds,
  selectedProductId,
  onToggleRow,
  onSelectOnly,
  onToggleAll,
  loading,
}: ProductListTableProps) {
  const orgPath = useOrgPath();
  const allSelected = rows.length > 0 && rows.every((row) => selectedIds.includes(row.id));

  return (
    <div className="productListTableShell">
      <div className="productListTableScroller">
        <table className="productListTable">
          <thead>
            <tr>
              <th className="productListTableCheckCol">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(event) => onToggleAll(event.target.checked)}
                  aria-label="Выбрать все товары на странице"
                />
              </th>
              <th>Товар</th>
              <th>Категория</th>
              <th>Группа</th>
              <th>Готовность</th>
              <th>Каналы</th>
              <th className="productListActionCol"></th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, index) => (
                  <tr key={`sk-${index}`} className="productListRow productListRowSkeleton">
                    <td><span className="productListSkeleton productListSkeletonCheck" /></td>
                    <td><span className="productListSkeleton productListSkeletonTitle" /></td>
                    <td><span className="productListSkeleton productListSkeletonMeta" /></td>
                    <td><span className="productListSkeleton productListSkeletonMeta" /></td>
                    <td><span className="productListSkeleton productListSkeletonChannels" /></td>
                    <td><span className="productListSkeleton productListSkeletonChannels" /></td>
                    <td><span className="productListSkeleton productListSkeletonAction" /></td>
                  </tr>
                ))
              : rows.map((product) => {
                  const title = String(product.title || product.name || "").trim() || product.id;
                  const sku = String(product.sku_gt || "").trim() || "Без SKU";
                  const templateName = String(product.effective_template_name || "").trim();
                  const category = compactCategoryPath(product.category_path);
                  const group = displayGroupName(product);
                  const nextStep = getProductNextStep(product);
                  const isSelected = selectedIds.includes(product.id);
                  const isFocused = selectedProductId === product.id;
                  return (
                    <tr
                      key={product.id}
                      className={`productListRow${isFocused ? " isFocused" : ""}${isSelected ? " isSelected" : ""}`}
                      onClick={() => onSelectOnly(product.id)}
                    >
                      <td className="productListTableCheckCol" onClick={(event) => event.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={(event) => onToggleRow(product.id, event.target.checked)}
                          aria-label={`Выбрать товар ${title}`}
                        />
                      </td>
                      <td>
                        <div className="productListTitleCell">
                          <div className="productListThumbWrap">
                            {product.preview_url ? (
                              <img className="productListThumb" src={product.preview_url} alt="" loading="lazy" />
                            ) : (
                              <div className="productListThumb productListThumbEmpty" aria-hidden="true">
                                SKU
                              </div>
                            )}
                          </div>
                          <div className="productListTitleMeta">
                            <Link
                              className="productListPrimaryLink"
                              to={orgPath(`/products/${encodeURIComponent(product.id)}`)}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {title}
                            </Link>
                            <div className="productListSku">{sku}</div>
                          </div>
                        </div>
                      </td>
                      <td>
                        <div className="productListCategoryCell">
                          <div className="productListCellMeta isStrong">{category.primary}</div>
                          {category.secondary ? <div className="productListCellSubtle">{category.secondary}</div> : null}
                        </div>
                      </td>
                      <td>
                        <div className="productListGroupCell">
                          <div className="productListCellMeta isStrong">{group.primary}</div>
                          {group.secondary ? <div className="productListCellSubtle">{group.secondary}</div> : null}
                        </div>
                      </td>
                      <td>
                        <div className="productListReadinessCell">
                          <ProductReadinessBadge product={product} />
                          <div className="productListNextStep">
                            <strong>{nextStep.title}</strong>
                            <div>{nextStep.detail}</div>
                          </div>
                          {templateName ? (
                            <Link
                              className="productListInlineLink"
                              to={orgPath(templateHref(product))}
                              onClick={(event) => event.stopPropagation()}
                            >
                              {templateName}
                            </Link>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <ProductChannelsCell product={product} />
                      </td>
                      <td className="productListActionCol" onClick={(event) => event.stopPropagation()}>
                        <Link className="btn productListRowAction" to={orgPath(nextStep.href)}>
                          {nextStep.cta}
                        </Link>
                        <Link className="productListOpenLink" to={orgPath(`/products/${encodeURIComponent(product.id)}`)}>
                          Открыть
                        </Link>
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProductBulkActionBar({
  selectedIds,
  categoryId,
  onClear,
  onDelete,
}: {
  selectedIds: string[];
  categoryId?: string;
  onClear: () => void;
  onDelete: () => void;
}) {
  const orgPath = useOrgPath();
  if (!selectedIds.length) return null;

  const first = selectedIds[0];

  return (
    <div className="productListBulkBar">
      <div className="productListBulkBarMeta">
        <strong>{selectedIds.length}</strong> SKU в выборе
      </div>
      <div className="productListBulkBarActions">
        <Link className="btn" to={orgPath(`/products/${encodeURIComponent(first)}`)}>
          Открыть первый
        </Link>
        <Link className="btn" to={orgPath(withProductExportHref(selectedIds))}>
          Проверить выбор
        </Link>
        <Link className="btn" to={orgPath("/sources?tab=sources")}>
          К сопоставлениям
        </Link>
        <Button variant="danger" onClick={onDelete}>Удалить выбранные</Button>
        <Button onClick={onClear}>Снять выбор</Button>
      </div>
    </div>
  );
}

function ProductCatalogScope({
  nodes,
  rootCategories,
  subCategories,
  parentCategoryId,
  subCategoryId,
  total,
  onParentChange,
  onSubChange,
  onCategorySelect,
  onClear,
}: {
  nodes: CatalogNode[];
  rootCategories: Array<{ id: string; name: string }>;
  subCategories: Array<{ id: string; path: string }>;
  parentCategoryId: string;
  subCategoryId: string;
  total: number;
  onParentChange: (id: string) => void;
  onSubChange: (id: string) => void;
  onCategorySelect: (rootId: string, nodeId: string) => void;
  onClear: () => void;
}) {
  const activeCategoryId = subCategoryId || parentCategoryId;
  const [expandedIds, setExpandedIds] = useState<Set<string>>(() => new Set(rootCategories.map((category) => category.id).slice(0, 3)));

  const treeData = useMemo(() => {
    const byId = new Map<string, CatalogNode>();
    const children = new Map<string, CatalogNode[]>();
    for (const node of nodes) {
      const id = String(node.id || "").trim();
      if (!id) continue;
      byId.set(id, node);
      const parentId = String(node.parent_id || "").trim();
      const bucket = children.get(parentId) || [];
      bucket.push(node);
      children.set(parentId, bucket);
    }
    for (const bucket of children.values()) {
      bucket.sort((left, right) => {
        if ((left.position || 0) !== (right.position || 0)) return (left.position || 0) - (right.position || 0);
        return (left.name || "").localeCompare(right.name || "", "ru");
      });
    }
    return { byId, children };
  }, [nodes]);

  useEffect(() => {
    if (!activeCategoryId) return;
    setExpandedIds((current) => {
      const next = new Set(current);
      let node = treeData.byId.get(activeCategoryId);
      const seen = new Set<string>();
      while (node && !seen.has(node.id)) {
        seen.add(node.id);
        next.add(node.id);
        const parentId = String(node.parent_id || "").trim();
        if (parentId) next.add(parentId);
        node = parentId ? treeData.byId.get(parentId) : undefined;
      }
      return next;
    });
  }, [activeCategoryId, treeData.byId]);

  const visibleTreeRows = useMemo(() => {
    const rows: Array<{ node: CatalogNode; depth: number; hasChildren: boolean; rootId: string }> = [];
    const walk = (node: CatalogNode, depth: number, rootId: string) => {
      const children = treeData.children.get(node.id) || [];
      rows.push({ node, depth, hasChildren: children.length > 0, rootId });
      if (!expandedIds.has(node.id)) return;
      for (const child of children) walk(child, depth + 1, rootId);
    };
    for (const root of treeData.children.get("") || []) walk(root, 0, root.id);
    return rows;
  }, [expandedIds, treeData.children]);

  useEffect(() => {
    if (expandedIds.size || !rootCategories.length) return;
    setExpandedIds(new Set(rootCategories.map((category) => category.id).slice(0, 3)));
  }, [expandedIds.size, rootCategories]);

  function toggleExpanded(id: string) {
    setExpandedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <aside className="productListCatalogPane">
      <div className="productListCatalogHead">
        <div>
          <strong>Каталог</strong>
          <span>{total} SKU в текущем срезе</span>
        </div>
        {(parentCategoryId || subCategoryId) ? (
          <button type="button" className="btn ghost" onClick={onClear}>Сброс</button>
        ) : null}
      </div>

      <div className="productListCatalogControls">
        <Select value={parentCategoryId} onChange={(event) => onParentChange(event.target.value)}>
          <option value="">Все разделы</option>
          {rootCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </Select>
        <Select value={subCategoryId} disabled={!parentCategoryId} onChange={(event) => onSubChange(event.target.value)}>
          <option value="">Вся ветка</option>
          {subCategories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.path}
            </option>
          ))}
        </Select>
      </div>

      <div className="productListCatalogTree">
        <button
          type="button"
          className={`productListCatalogNode${!parentCategoryId ? " isActive" : ""}`}
          onClick={onClear}
        >
          <span>Весь каталог</span>
          <span className="productListCatalogNodeCount">{total}</span>
        </button>
        {visibleTreeRows.map(({ node, depth, hasChildren, rootId }) => {
          const isActive = activeCategoryId === node.id;
          const isExpanded = expandedIds.has(node.id);
          return (
            <div
              key={node.id}
              className={`productListCatalogTreeRow${isActive ? " isActive" : ""}`}
              style={{ ["--depth" as never]: depth }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  className={`productListCatalogCaret${isExpanded ? " isExpanded" : ""}`}
                  onClick={() => toggleExpanded(node.id)}
                  aria-label={isExpanded ? "Свернуть категорию" : "Раскрыть категорию"}
                >
                  ›
                </button>
              ) : (
                <span className="productListCatalogCaretSpacer" aria-hidden />
              )}
              <button
                type="button"
                className="productListCatalogNode"
                onClick={() => onCategorySelect(rootId, depth === 0 ? "" : node.id)}
                title={node.name}
              >
                <span>{node.name}</span>
                <span className="productListCatalogNodeCount">
                  {hasChildren ? (isExpanded ? "−" : "+") : (node.products_count || "")}
                </span>
              </button>
            </div>
          );
        })}
      </div>
    </aside>
  );
}

export default function ProductListFeature() {
  const [searchParams, setSearchParams] = useSearchParams();
  const orgPath = useOrgPath();
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [isFallbackMode, setIsFallbackMode] = useState(false);
  const [products, setProducts] = useState<ProductItem[]>([]);
  const [nodes, setNodes] = useState<CatalogNode[]>([]);
  const [groups, setGroups] = useState<GroupItem[]>([]);
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [searchDraft, setSearchDraft] = useState(searchParams.get("q") || "");
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const [refreshToken, setRefreshToken] = useState(0);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkDeleteSaving, setBulkDeleteSaving] = useState(false);

  const query = searchParams.get("q") || "";
  const deferredSearchDraft = useDeferredValue(searchDraft);
  const categoryParam = searchParams.get("category") || "";
  const parentCategoryId = searchParams.get("parent") || categoryParam;
  const subCategoryId = searchParams.get("sub") || "";
  const groupFilter = searchParams.get("group") || "";
  const templateFilter = searchParams.get("template") || "";
  const marketFilter =
    searchParams.get("ym") === "on" || searchParams.get("ym") === "off"
      ? (searchParams.get("ym") as "on" | "off")
      : "all";
  const ozonFilter =
    searchParams.get("oz") === "on" || searchParams.get("oz") === "off"
      ? (searchParams.get("oz") as "on" | "off")
      : "all";
  const queueMode = (searchParams.get("view") as QueueMode) || "all";
  const currentPage = Math.max(1, Number(searchParams.get("page") || "1") || 1);

  function updateFilters(
    patch: Partial<{
      q: string;
      parent: string;
      sub: string;
      group: string;
      template: string;
      ym: "all" | "on" | "off";
      oz: "all" | "on" | "off";
      view: QueueMode;
      page: number;
    }>,
  ) {
    startTransition(() => {
      const next = new URLSearchParams(searchParams);
      const apply = (key: string, value: string) => {
        if (value) next.set(key, value);
        else next.delete(key);
      };

      if (patch.q !== undefined) apply("q", patch.q);
      if (patch.parent !== undefined) {
        apply("parent", patch.parent);
        next.delete("category");
      }
      if (patch.sub !== undefined) apply("sub", patch.sub);
      if (patch.group !== undefined) apply("group", patch.group);
      if (patch.template !== undefined) apply("template", patch.template);
      if (patch.ym !== undefined) patch.ym === "all" ? next.delete("ym") : next.set("ym", patch.ym);
      if (patch.oz !== undefined) patch.oz === "all" ? next.delete("oz") : next.set("oz", patch.oz);
      if (patch.view !== undefined) patch.view === "all" ? next.delete("view") : next.set("view", patch.view);
      if (patch.page !== undefined) {
        if (patch.page > 1) next.set("page", String(patch.page));
        else next.delete("page");
      }
      setSearchParams(next, { replace: true });
    });
  }

  useEffect(() => {
    setSearchDraft(query);
  }, [query]);

  useEffect(() => {
    const next = deferredSearchDraft.trim();
    if (next === query) return;
    const timeoutId = window.setTimeout(() => {
      updateFilters({ q: next, page: 1 });
    }, 220);
    return () => window.clearTimeout(timeoutId);
  }, [deferredSearchDraft, query]);

  useEffect(() => {
    const controller = new AbortController();
    const nodeById = new Map<string, CatalogNode>();

    function normalize(value: unknown): string {
      return String(value || "").trim().toLowerCase();
    }

    function toFallbackProductRows(items: CoreCatalogProductResp["items"], catalogNodes: CatalogNode[]): ProductItem[] {
      for (const node of catalogNodes) nodeById.set(node.id, node);
      let rows = items.map((item) => {
        const id = String(item.id || "").trim();
        const categoryId = String(item.category_id || "").trim();
        return {
          id,
          title: String(item.title || item.name || "").trim(),
          name: String(item.title || item.name || "").trim(),
          category_id: categoryId,
          category_path: buildCategoryPath(nodeById, categoryId),
          sku_pim: String(item.sku_pim || "").trim(),
          sku_gt: String(item.sku_gt || "").trim(),
          preview_url: String(item.preview_url || "").trim(),
          group_id: String(item.group_id || "").trim(),
          group_name: String(item.group_id || "").trim(),
          marketplace_statuses: {},
          effective_template_id: "",
          effective_template_name: "",
          effective_template_source_category_id: "",
        } satisfies ProductItem;
      });

      if (parentCategoryId) {
        const allowed = new Set<string>();
        const stack = [parentCategoryId];
        while (stack.length) {
          const nextId = stack.pop() as string;
          if (allowed.has(nextId)) continue;
          allowed.add(nextId);
          for (const node of catalogNodes) {
            if (String(node.parent_id || "") === nextId) stack.push(node.id);
          }
        }
        rows = rows.filter((row) => allowed.has(row.category_id));
      }

      if (subCategoryId) {
        const allowed = new Set<string>();
        const stack = [subCategoryId];
        while (stack.length) {
          const nextId = stack.pop() as string;
          if (allowed.has(nextId)) continue;
          allowed.add(nextId);
          for (const node of catalogNodes) {
            if (String(node.parent_id || "") === nextId) stack.push(node.id);
          }
        }
        rows = rows.filter((row) => allowed.has(row.category_id));
      }

      if (groupFilter === "__ungrouped__") rows = rows.filter((row) => !row.group_id);
      else if (groupFilter) rows = rows.filter((row) => row.group_id === groupFilter);

      if (query) {
        const qn = normalize(query);
        rows = rows.filter((row) =>
          [row.title, row.name, row.sku_gt, row.sku_pim, row.group_name, row.category_path].some((value) =>
            normalize(value).includes(qn),
          ),
        );
      }

      if (queueMode === "no_template") rows = rows.filter((row) => !row.effective_template_name);

      rows.sort((left, right) =>
        normalize(left.sku_gt || left.title || left.id).localeCompare(normalize(right.sku_gt || right.title || right.id), "ru"),
      );
      return rows;
    }

    setLoading(true);
    setLoadError("");
    setIsFallbackMode(false);

    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (parentCategoryId) params.set("parent", parentCategoryId);
    if (subCategoryId) params.set("sub", subCategoryId);
    if (groupFilter) params.set("group", groupFilter);
    if (templateFilter) params.set("template", templateFilter);
    if (marketFilter !== "all") params.set("ym", marketFilter);
    if (ozonFilter !== "all") params.set("oz", ozonFilter);
    if (queueMode !== "all") params.set("view", queueMode);
    params.set("page", String(currentPage));
    params.set("page_size", String(DEFAULT_PAGE_SIZE));

    const richController = new AbortController();
    const richTimeout = window.setTimeout(() => richController.abort(), RICH_PRODUCTS_TIMEOUT_MS);

    api<ProductsPageDataResp>(`/catalog/products-page-data?${params.toString()}`, { signal: richController.signal })
      .then((data) => {
        window.clearTimeout(richTimeout);
        if (controller.signal.aborted) return;
        setProducts(Array.isArray(data.products) ? data.products : []);
        setNodes(Array.isArray(data.nodes) ? data.nodes : []);
        setGroups(Array.isArray(data.groups) ? data.groups : []);
        setTemplates(Array.isArray(data.templates) ? data.templates : []);
        setTotal(Math.max(0, Number(data.total || 0)));
        setPageSize(Math.max(1, Number(data.page_size || DEFAULT_PAGE_SIZE)));
      })
      .catch(async (error) => {
        window.clearTimeout(richTimeout);
        if (controller.signal.aborted) return;
        try {
          const fallbackController = new AbortController();
          const fallbackTimeout = window.setTimeout(() => fallbackController.abort(), RICH_PRODUCTS_TIMEOUT_MS);
          const abortFallback = () => fallbackController.abort();
          controller.signal.addEventListener("abort", abortFallback, { once: true });
          try {
            const [catalogNodes, coreProducts] = await Promise.all([
              api<{ nodes: CatalogNode[] }>("/catalog/nodes", { signal: fallbackController.signal }),
              api<CoreCatalogProductResp>("/catalog/products", { signal: fallbackController.signal }),
            ]);
            if (controller.signal.aborted) return;
            const fallbackRows = toFallbackProductRows(coreProducts.items || [], catalogNodes.nodes || []);
            const pageOffset = (currentPage - 1) * DEFAULT_PAGE_SIZE;
            const pagedRows = fallbackRows.slice(pageOffset, pageOffset + DEFAULT_PAGE_SIZE);
            setProducts(pagedRows);
            setNodes(Array.isArray(catalogNodes.nodes) ? catalogNodes.nodes : []);
            setGroups([]);
            setTemplates([]);
            setTotal(fallbackRows.length);
            setPageSize(DEFAULT_PAGE_SIZE);
            setIsFallbackMode(true);
            setLoadError("");
          } finally {
            window.clearTimeout(fallbackTimeout);
            controller.signal.removeEventListener("abort", abortFallback);
          }
        } catch (fallbackError) {
          if (controller.signal.aborted) return;
          setProducts([]);
          const fallbackMessage = fallbackError instanceof DOMException && fallbackError.name === "AbortError"
            ? "Каталог отвечает слишком долго. Попробуй обновить страницу или проверить очередь товаров."
            : (fallbackError as Error).message || (error as Error).message || "Не удалось загрузить очередь товаров";
          setLoadError(fallbackMessage);
        }
      })
      .finally(() => {
        window.clearTimeout(richTimeout);
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => {
      controller.abort();
      richController.abort();
      window.clearTimeout(richTimeout);
    };
  }, [query, parentCategoryId, subCategoryId, groupFilter, templateFilter, marketFilter, ozonFilter, queueMode, currentPage, refreshToken]);

  useEffect(() => {
    setSelectedIds((current) => current.filter((id) => products.some((product) => product.id === id)));
    setSelectedProductId((current) => {
      if (current && products.some((product) => product.id === current)) return current;
      return products[0]?.id || null;
    });
  }, [products]);

  const selectedProduct = useMemo(
    () => products.find((product) => product.id === selectedProductId) || null,
    [products, selectedProductId],
  );

  const childrenByParent = useMemo(() => {
    const map = new Map<string, CatalogNode[]>();
    for (const node of nodes) {
      const key = node.parent_id || "";
      const bucket = map.get(key) || [];
      bucket.push(node);
      map.set(key, bucket);
    }
    for (const bucket of map.values()) {
      bucket.sort((left, right) => {
        if ((left.position || 0) !== (right.position || 0)) return (left.position || 0) - (right.position || 0);
        return (left.name || "").localeCompare(right.name || "", "ru");
      });
    }
    return map;
  }, [nodes]);

  const nodeById = useMemo(() => {
    const map = new Map<string, CatalogNode>();
    for (const node of nodes) map.set(String(node.id || ""), node);
    return map;
  }, [nodes]);
  const activeCategoryId = subCategoryId || parentCategoryId;
  const activeCategory = activeCategoryId ? nodeById.get(activeCategoryId) || null : null;

  const rootCategories = useMemo(
    () => (childrenByParent.get("") || []).map((node) => ({ id: node.id, name: node.name })),
    [childrenByParent],
  );

  const subCategories = useMemo(() => {
    if (!parentCategoryId) return [] as Array<{ id: string; path: string }>;

    const pathCache = new Map<string, string>();
    const buildPath = (categoryId: string): string => {
      if (!categoryId) return "";
      if (pathCache.has(categoryId)) return pathCache.get(categoryId) || "";
      const node = nodeById.get(categoryId);
      if (!node) return "";
      const parentPath = node.parent_id ? buildPath(String(node.parent_id)) : "";
      const path = parentPath ? `${parentPath} / ${node.name}` : node.name;
      pathCache.set(categoryId, path);
      return path;
    };

    const list: Array<{ id: string; path: string }> = [];
    const stack = [...(childrenByParent.get(parentCategoryId) || [])];
    while (stack.length) {
      const node = stack.shift() as CatalogNode;
      list.push({ id: node.id, path: buildPath(node.id) || node.name });
      const children = childrenByParent.get(node.id) || [];
      for (const child of children) stack.push(child);
    }
    list.sort((left, right) => left.path.localeCompare(right.path, "ru"));
    return list;
  }, [childrenByParent, nodeById, parentCategoryId]);

  const totalPages = Math.max(1, Math.ceil(total / Math.max(1, pageSize)));
  const pageFrom = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const pageTo = Math.min(total, currentPage * pageSize);
  const hasActiveFilters = Boolean(
    query || parentCategoryId || subCategoryId || groupFilter || templateFilter || marketFilter !== "all" || ozonFilter !== "all" || queueMode !== "all",
  );

  function handleToggleRow(id: string, checked: boolean) {
    setSelectedIds((current) => {
      if (checked) return Array.from(new Set([...current, id]));
      return current.filter((item) => item !== id);
    });
    setSelectedProductId(id);
    setInspectorOpen(true);
  }

  function handleSelectOnly(id: string) {
    setSelectedProductId(id);
    setInspectorOpen(true);
  }

  function handleToggleAll(checked: boolean) {
    if (checked) {
      setSelectedIds(products.map((product) => product.id));
      if (!selectedProductId && products[0]) setSelectedProductId(products[0].id);
      return;
    }
    setSelectedIds([]);
  }

  async function confirmDeleteSelectedProducts() {
    if (!selectedIds.length) return;
    setLoadError("");
    setBulkDeleteSaving(true);
    try {
      await api("/catalog/products/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ ids: selectedIds }),
      });
      setSelectedIds([]);
      setSelectedProductId(null);
      setBulkDeleteOpen(false);
      setRefreshToken((value) => value + 1);
    } catch (error) {
      setLoadError((error as Error).message || "Не удалось удалить товары");
    } finally {
      setBulkDeleteSaving(false);
    }
  }

  return (
    <div className="productListPage">
      <ProductListEntryBar
        total={total}
        visibleCount={products.length}
        queueMode={queueMode}
        selectedCount={selectedIds.length}
        categoryId={activeCategoryId}
        categoryName={activeCategory?.name || ""}
        directCount={activeCategory?.products_count || 0}
      />

      {loadError ? <Alert tone="error">{loadError}</Alert> : null}
      {!loadError && isFallbackMode ? (
        <Alert tone="info">
          Расширенный список товаров не ответил вовремя. Показан базовый список SKU без полной проверки каналов и моделей категорий.
        </Alert>
      ) : null}

      <ProductListSummaryStrip
        rows={products}
        total={total}
        selectedCount={selectedIds.length}
        loading={loading}
      />

      <DataToolbar
        className="productListToolbar"
        title="Фильтры очереди"
        subtitle="Оставьте на экране только SKU, по которым нужно принять решение."
        actions={
          hasActiveFilters ? (
            <Button
              onClick={() =>
                updateFilters({
                  q: "",
                  parent: "",
                  sub: "",
                  group: "",
                  template: "",
                  ym: "all",
                  oz: "all",
                  view: "all",
                  page: 1,
                })
              }
            >
              Сбросить
            </Button>
          ) : null
        }
        compact
      >
        <div className="productListToolbarContent">
          <div className="productListToolbarTop">
            <div className="productListToolbarSearch">
              <TextInput
                className="pn-input productListSearchInput"
                placeholder="Поиск по названию, SKU и группе..."
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
              />
            </div>
            <ProductQueueSwitch mode={queueMode} onChange={(next) => updateFilters({ view: next, page: 1 })} />
          </div>

          <div className="productListFiltersGrid" aria-label="Фильтры товаров">
            <Select value={parentCategoryId} onChange={(event) => updateFilters({ parent: event.target.value, sub: "", page: 1 })}>
              <option value="">Все категории</option>
              {rootCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </Select>

            <Select
              value={subCategoryId}
              disabled={!parentCategoryId}
              onChange={(event) => updateFilters({ sub: event.target.value, page: 1 })}
            >
              <option value="">Все подкатегории</option>
              {subCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.path}
                </option>
              ))}
            </Select>

            <Select value={groupFilter} onChange={(event) => updateFilters({ group: event.target.value, page: 1 })}>
              <option value="">Все группы</option>
              <option value="__ungrouped__">Без группы</option>
              {groups
                .slice()
                .sort((left, right) => left.name.localeCompare(right.name, "ru"))
                .map((group) => (
                  <option key={group.id} value={group.id}>
                    {group.name}
                  </option>
                ))}
            </Select>

            <Select value={templateFilter} onChange={(event) => updateFilters({ template: event.target.value, page: 1 })}>
              <option value="">Все модели</option>
              <option value="__without__">Без модели</option>
              {templates
                .slice()
                .sort((left, right) => left.name.localeCompare(right.name, "ru"))
                .map((template) => (
                  <option key={template.id} value={template.id}>
                    {template.name}
                  </option>
                ))}
            </Select>

            <Select value={marketFilter} onChange={(event) => updateFilters({ ym: event.target.value as "all" | "on" | "off", page: 1 })}>
              <option value="all">Я.Маркет: все</option>
              <option value="on">Я.Маркет: включено</option>
              <option value="off">Я.Маркет: не готово</option>
            </Select>

            <Select value={ozonFilter} onChange={(event) => updateFilters({ oz: event.target.value as "all" | "on" | "off", page: 1 })}>
              <option value="all">Ozon: все</option>
              <option value="on">Ozon: включено</option>
              <option value="off">Ozon: не готово</option>
            </Select>
          </div>
        </div>
      </DataToolbar>

      {products.length === 0 && !loading ? (
        <EmptyState
          title="Товары не найдены"
          description="Попробуйте сменить режим очереди или снять часть фильтров. Страница должна оставаться рабочим входом в SKU даже при пустом результате."
          action={
            hasActiveFilters ? (
              <Button
                onClick={() =>
                  updateFilters({
                    q: "",
                    parent: "",
                    sub: "",
                    group: "",
                    template: "",
                    ym: "all",
                    oz: "all",
                    view: "all",
                    page: 1,
                  })
                }
              >
                Сбросить фильтры
              </Button>
            ) : (
              <Link className="btn primary" to={orgPath("/products/new")}>
                Создать первый товар
              </Link>
            )
          }
        />
      ) : (
        <>
          <div className="productListWorkspace">
            <ProductCatalogScope
              nodes={nodes}
              rootCategories={rootCategories}
              subCategories={subCategories}
              parentCategoryId={parentCategoryId}
              subCategoryId={subCategoryId}
              total={total}
              onParentChange={(id) => updateFilters({ parent: id, sub: "", page: 1 })}
              onSubChange={(id) => updateFilters({ sub: id, page: 1 })}
              onCategorySelect={(rootId, nodeId) => updateFilters({ parent: rootId, sub: nodeId, page: 1 })}
              onClear={() => updateFilters({ parent: "", sub: "", page: 1 })}
            />

            <div className="productListMainStack">
              <Card className="productListTableCard">
                <div className="productListTableHead">
                  <div>
                    <div className="productListTableTitle">SKU в работе</div>
                    <div className="productListTableSubtitle">
                      Показано <strong>{pageFrom}-{pageTo}</strong> из <strong>{total}</strong>
                    </div>
                  </div>
                  <div className="productListPager">
                    <Button disabled={currentPage <= 1 || loading} onClick={() => updateFilters({ page: currentPage - 1 })}>
                      Назад
                    </Button>
                    <div className="productListPagerMeta">
                      Страница {currentPage} / {totalPages}
                    </div>
                    <Button disabled={currentPage >= totalPages || loading} onClick={() => updateFilters({ page: currentPage + 1 })}>
                      Дальше
                    </Button>
                  </div>
                </div>

                <ProductListTable
                  rows={products}
                  selectedIds={selectedIds}
                  selectedProductId={selectedProductId}
                  onToggleRow={handleToggleRow}
                  onSelectOnly={handleSelectOnly}
                  onToggleAll={handleToggleAll}
                  loading={loading}
                />
              </Card>

              <ProductBulkActionBar
                selectedIds={selectedIds}
                categoryId={activeCategoryId}
                onClear={() => setSelectedIds([])}
                onDelete={() => setBulkDeleteOpen(true)}
              />
            </div>
          </div>
          <ProductListInspector
            product={selectedProduct}
            selectedCount={selectedIds.length}
            onClearSelection={() => setSelectedIds([])}
            open={inspectorOpen}
            onClose={() => setInspectorOpen(false)}
          />
        </>
      )}
      {bulkDeleteOpen ? (
        <div className="modalBackdrop" role="presentation" onMouseDown={() => !bulkDeleteSaving && setBulkDeleteOpen(false)}>
          <div className="modalCard modalCardCompact" role="dialog" aria-modal="true" aria-labelledby="bulk-delete-products-title" onMouseDown={(event) => event.stopPropagation()}>
            <div className="modalHeader">
              <div>
                <div className="modalTitle" id="bulk-delete-products-title">Удалить выбранные SKU</div>
                <div className="modalSubtitle">
                  Выбранные товары уйдут из каталога, групп, рабочих привязок и очереди выгрузки. Действие нельзя отменить.
                </div>
              </div>
            </div>
            <div className="productListDeleteSummary">
              <strong>{selectedIds.length}</strong>
              <span>SKU в выборе</span>
            </div>
            <div className="productListModalActions">
              <Button onClick={() => setBulkDeleteOpen(false)} disabled={bulkDeleteSaving}>Отмена</Button>
              <Button variant="danger" onClick={() => void confirmDeleteSelectedProducts()} disabled={bulkDeleteSaving || !selectedIds.length}>
                {bulkDeleteSaving ? "Удаляем..." : "Удалить SKU"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
