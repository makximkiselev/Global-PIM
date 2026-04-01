import { DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import "../styles/product-new.css";
import "../styles/product.css";
import "../styles/product-groups.css";
import { api } from "../lib/api";
import { toRenderableMediaUrl } from "../lib/media";

type CatalogNode = {
  id: string;
  parent_id: string | null;
  name: string;
  position: number;
};

type CatalogProductItem = {
  id: string;
  title?: string;
  name?: string;
  category_id?: string;
  sku_pim?: string;
  sku_gt?: string;
  sku_id?: string;
};

type ProductFeature = {
  code?: string;
  name: string;
  value: string;
};

type ProductRelation = {
  id?: string;
  sku?: string;
  name: string;
  sku_gt?: string;
  sku_id?: string;
};

type ProductT = {
  id: string;
  category_id: string;
  type: "single" | "multi";
  status: "draft" | "active" | "archived";
  title: string;
  group_id?: string;
  sku_pim?: string;
  sku_gt?: string;
  sku_id?: string;
  created_at?: string;
  updated_at?: string;
  exports_enabled?: Record<string, boolean>;
  content?: ProductContent;
};

type VariantT = {
  id: string;
  product_id: string;
  sku: string;
  options: Record<string, string>;
  status: string;
};

type ProductContent = {
  description: string;
  media: { url: string; caption?: string }[]; // legacy fallback
  media_images: { url: string; caption?: string }[];
  media_videos: { url: string; caption?: string }[];
  media_cover: { url: string; caption?: string }[];
  documents: { name: string; url: string }[];
  links: { label: string; url: string }[];
  features: ProductFeature[];
  analogs: ProductRelation[];
  related: ProductRelation[];
};

type FeatureDef = {
  code: string;
  name: string;
  required?: boolean;
};

type DisplayFeatureRow = {
  key: string;
  code: string;
  name: string;
  value: string;
  required: boolean;
  template: boolean;
};

type ProductResp = { product: ProductT; variants?: VariantT[] };
type MarketplaceChannel = {
  title: string;
  status: string;
  content_rating: string;
  stores_count?: number;
  stores?: Array<{ store_id: string; store_title: string; business_id?: string; status: string; content_rating?: number | string }>;
};
type ExternalSystemChannel = { title: string; status: string };
type CompetitorChannel = { key: "restore" | "store77"; title: string; status: string; url: string };
type ChannelsSummaryResp = {
  marketplaces: MarketplaceChannel[];
  external_systems: ExternalSystemChannel[];
  competitors: CompetitorChannel[];
};

const defaultChannelsSummary = (): ChannelsSummaryResp => ({
  marketplaces: [
    { title: "Я.Маркет", status: "Нет данных", content_rating: "Нет данных", stores_count: 0, stores: [] },
    { title: "OZON", status: "Нет данных", content_rating: "Нет данных", stores_count: 0, stores: [] },
    { title: "Wildberries", status: "Нет данных", content_rating: "Нет данных", stores_count: 0, stores: [] },
  ],
  external_systems: [
    { title: "Сайт", status: "Заглушка" },
    { title: "1С", status: "Заглушка" },
  ],
  competitors: [
    { key: "restore", title: "Re:Store", status: "Не задан", url: "" },
    { key: "store77", title: "Store77", status: "Не задан", url: "" },
  ],
});

function channelTone(status: string): "ok" | "warn" | "muted" {
  const s = displayChannelStatus(status).toLowerCase();
  if (!s || s.includes("нет данных") || s.includes("не задан") || s.includes("заглушка")) return "muted";
  if (s.includes("все ок")) return "ok";
  if (s.includes("обновляется")) return "warn";
  if (s.includes("есть расхождения") || s.includes("ошибка")) return "warn";
  if (s.includes("продается")) return "ok";
  return "warn";
}

function displayChannelStatus(status: string): string {
  const s = String(status || "").trim().toLowerCase();
  if (!s || s.includes("нет данных")) return "Нет данных";
  if (s.includes("не задан")) return "Не задан";
  if (s.includes("заглушка")) return "Заглушка";
  if (s.includes("обновляется") || s.includes("импортируется")) return "Обновляется";
  if (s.includes("есть расхождения")) return "Есть расхождения";
  if (
    s.includes("ошибка") ||
    s.includes("error") ||
    s.includes("fail") ||
    s.includes("rejected") ||
    s.includes("problem")
  ) return "Ошибка";
  if (
    s.includes("продается") ||
    s.includes("карточка есть") ||
    s.includes("готов") ||
    s.includes("approved") ||
    s.includes("успеш") ||
    s.includes("imported")
  ) return "Все ок";
  return "Ошибка";
}

function ratingScore(value: string | number | undefined | null): number | null {
  if (value == null) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const nums = raw.match(/\d+(?:\.\d+)?/g);
  if (!nums || !nums.length) return null;
  const parsed = nums.map((x) => Number(x)).filter((x) => Number.isFinite(x));
  if (!parsed.length) return null;
  const avg = parsed.reduce((a, b) => a + b, 0) / parsed.length;
  return Math.max(0, Math.min(100, avg));
}

function ratingStyle(value: string | number | undefined | null) {
  const score = ratingScore(value);
  if (score == null) return undefined;
  const hue = Math.round((score / 100) * 120);
  return {
    "--score-hue": String(hue),
    "--score-fill": `${score}%`,
  } as const;
}

function statusDotLabel(status: string): string {
  const tone = channelTone(status);
  if (tone === "ok") return "Все ок";
  if (tone === "warn") return displayChannelStatus(status);
  return "Нет данных";
}

function marketplaceOverviewTone(item: MarketplaceChannel): "ok" | "muted" {
  return item.stores?.length ? "ok" : "muted";
}

function marketplaceStoreCountLabel(item: MarketplaceChannel): string {
  return item.stores?.length
    ? `${item.stores.length} магазин${item.stores.length === 1 ? "" : item.stores.length < 5 ? "а" : "ов"}`
    : "-";
}
type GroupProductItem = {
  id: string;
  title?: string;
  name?: string;
  sku_gt?: string;
  sku_id?: string;
  category_id?: string;
};
type GroupDetailsResp = {
  group: { id: string; name: string; variant_param_ids?: string[] };
  items: GroupProductItem[];
};

type VariantParam = { id: string; name: string; code?: string; selected?: boolean };
type VariantParamsResp = { items: VariantParam[]; selected_ids?: string[] };
type TemplatesByCategoryResp = {
  template?: { id: string } | null;
  attributes?: Array<{
    id?: string;
    name?: string;
    code?: string;
    scope?: string;
    locked?: boolean;
    required?: boolean;
    options?: { layer?: string; param_group?: string; [key: string]: any };
  }>;
};

const emptyContent: ProductContent = {
  description: "",
  media: [],
  media_images: [],
  media_videos: [],
  media_cover: [],
  documents: [],
  links: [],
  features: [],
  analogs: [],
  related: [],
};

const AUTHORIZED_SITES = [
  { key: "restore", label: "restore", hostIncludes: ["restore"] },
  { key: "store77", label: "store77", hostIncludes: ["store77", "77"] },
] as const;

function buildPath(nodesById: Map<string, CatalogNode>, id: string): string {
  const chain: string[] = [];
  let cur = nodesById.get(id);
  const guard = new Set<string>();
  while (cur) {
    if (guard.has(cur.id)) break;
    guard.add(cur.id);
    chain.push(cur.name);
    cur = cur.parent_id ? nodesById.get(cur.parent_id) : undefined;
  }
  return chain.reverse().join(" / ");
}

function mergeContent(base: ProductContent, patch: Partial<ProductContent>): ProductContent {
  return {
    ...base,
    ...patch,
  };
}

function normalizeMediaItems(list: any): { url: string; caption?: string }[] {
  if (!Array.isArray(list)) return [];
  return list
    .map((x) => {
      if (!x || typeof x !== "object") return null;
      const url = String((x as any).url || "").trim();
      if (!url) return null;
      const caption = String((x as any).caption || "").trim();
      return caption ? { url, caption } : { url };
    })
    .filter(Boolean) as { url: string; caption?: string }[];
}

function normalizeContent(raw: Partial<ProductContent> | null | undefined): ProductContent {
  const merged = mergeContent(emptyContent, raw || {});
  const images = normalizeMediaItems(merged.media_images?.length ? merged.media_images : merged.media);
  const videos = normalizeMediaItems(merged.media_videos);
  const cover = normalizeMediaItems(merged.media_cover).slice(0, 1);
  return {
    ...merged,
    media_images: images,
    media_videos: videos,
    media_cover: cover,
    media: images,
  };
}

function toDisplayTitle(p: { title?: string; name?: string; id?: string }) {
  return (p.title || p.name || "").trim() || p.id || "";
}

function toSkuLine(p: { sku_gt?: string; sku_id?: string }) {
  return `GT: ${p.sku_gt || "-"} | IDS: ${p.sku_id || "-"}`;
}

function qnorm(s: string) {
  return (s || "").trim().toLowerCase();
}

function isFeatureAttr(attr: { code?: string; options?: { layer?: string; param_group?: string } }) {
  const code = qnorm(attr.code || "");
  const layer = qnorm(attr.options?.layer || "");
  const group = qnorm(attr.options?.param_group || "");
  if (layer === "base" && ["описание", "медиа"].includes(group)) return false;
  if (["description", "media_images", "media_videos", "media_cover", "title", "group_id", "sku_pim", "sku_gt", "sku_id"].includes(code)) {
    return false;
  }
  return true;
}

function parseHost(url: string) {
  try {
    return new URL(url).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function renderDescriptionHtml(source: string) {
  const text = String(source || "");
  if (!text.trim()) return "";
  if (/<[a-z][\s\S]*>/i.test(text)) return text;
  const escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return escaped
    .split(/\n{2,}/)
    .map((block) => `<p>${block.replace(/\n/g, "<br />")}</p>`)
    .join("");
}

export default function Product() {
  const { productId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [product, setProduct] = useState<ProductT | null>(null);
  const [groupName, setGroupName] = useState("");
  const [groupItems, setGroupItems] = useState<GroupProductItem[]>([]);
  const [groupVariantParams, setGroupVariantParams] = useState<VariantParam[]>([]);
  const [groupFilterByParam, setGroupFilterByParam] = useState<Record<string, string>>({});
  const [groupItemFeatures, setGroupItemFeatures] = useState<Record<string, ProductFeature[]>>({});
  const [channelsSummary, setChannelsSummary] = useState<ChannelsSummaryResp>(defaultChannelsSummary);
  const [openMarketplace, setOpenMarketplace] = useState("");

  const [catalogNodes, setCatalogNodes] = useState<CatalogNode[]>([]);
  const [allProducts, setAllProducts] = useState<CatalogProductItem[]>([]);

  const [tab, setTabState] = useState<
    "variants" | "media" | "features" | "description" | "documents" | "analogs" | "related"
  >((() => {
    const raw = searchParams.get("tab");
    return raw === "media" || raw === "features" || raw === "description" || raw === "documents" || raw === "analogs" || raw === "related"
      ? raw
      : "variants";
  })());

  const [title, setTitle] = useState("");
  const [status, setStatus] = useState<ProductT["status"]>("draft");
  const [skuPim, setSkuPim] = useState("");
  const [skuGt, setSkuGt] = useState("");
  const [skuId, setSkuId] = useState("");
  const [content, setContent] = useState<ProductContent>(emptyContent);
  const [originalRelatedIds, setOriginalRelatedIds] = useState<string[]>([]);

  const [featureDefs, setFeatureDefs] = useState<FeatureDef[]>([]);
  const [seoSourceA, setSeoSourceA] = useState("");
  const [seoSourceB, setSeoSourceB] = useState("");
  const [seoKeywords, setSeoKeywords] = useState("");
  const [seoProfile, setSeoProfileState] = useState<"fast" | "balanced" | "quality">(
    searchParams.get("seoProfile") === "fast" || searchParams.get("seoProfile") === "quality"
      ? (searchParams.get("seoProfile") as "fast" | "quality")
      : "balanced"
  );
  const [seoUseFeatures, setSeoUseFeatures] = useState(true);
  const [descriptionView, setDescriptionViewState] = useState<"preview" | "edit">(
    searchParams.get("descView") === "edit" ? "edit" : "preview"
  );
  const [seoLoading, setSeoLoading] = useState(false);

  const [selectModalKind, setSelectModalKind] = useState<"analogs" | "related" | null>(null);
  const [selectQuery, setSelectQuery] = useState("");
  const [videoModalUrl, setVideoModalUrl] = useState("");
  const [videoModalTitle, setVideoModalTitle] = useState("");
  const [imageModalIndex, setImageModalIndex] = useState<number | null>(null);
  const [competitorModalKey, setCompetitorModalKey] = useState<"restore" | "store77" | null>(null);
  const [competitorModalValue, setCompetitorModalValue] = useState("");
  const [heroImageIndex, setHeroImageIndex] = useState(0);
  const [groupItemPreviewUrls, setGroupItemPreviewUrls] = useState<Record<string, string>>({});
  const [pendingDelete, setPendingDelete] = useState<
    null | {
      kind: "media_images" | "media_images_bulk" | "media_videos" | "media_cover" | "documents";
      index?: number;
      indexes?: number[];
      url?: string;
      urls?: string[];
    }
  >(null);

  useEffect(() => {
    const raw = searchParams.get("tab");
    const next =
      raw === "media" || raw === "features" || raw === "description" || raw === "documents" || raw === "analogs" || raw === "related"
        ? raw
        : "variants";
    setTabState(next);
  }, [searchParams]);

  useEffect(() => {
    setSeoProfileState(
      searchParams.get("seoProfile") === "fast" || searchParams.get("seoProfile") === "quality"
        ? (searchParams.get("seoProfile") as "fast" | "quality")
        : "balanced"
    );
    setDescriptionViewState(searchParams.get("descView") === "edit" ? "edit" : "preview");
  }, [searchParams]);

  function setTab(
    nextTab: "variants" | "media" | "features" | "description" | "documents" | "analogs" | "related"
  ) {
    setTabState(nextTab);
    const next = new URLSearchParams(searchParams);
    next.set("tab", nextTab);
    setSearchParams(next, { replace: true });
  }

  function setSeoProfile(nextProfile: "fast" | "balanced" | "quality") {
    setSeoProfileState(nextProfile);
    const next = new URLSearchParams(searchParams);
    if (nextProfile === "balanced") next.delete("seoProfile");
    else next.set("seoProfile", nextProfile);
    setSearchParams(next, { replace: true });
  }

  function setDescriptionView(nextView: "preview" | "edit") {
    setDescriptionViewState(nextView);
    const next = new URLSearchParams(searchParams);
    if (nextView === "preview") next.delete("descView");
    else next.set("descView", nextView);
    setSearchParams(next, { replace: true });
  }
  const [selectedImageIndexes, setSelectedImageIndexes] = useState<number[]>([]);
  const variantsSectionRef = useRef<HTMLDivElement | null>(null);

  const nodesById = useMemo(() => new Map(catalogNodes.map((n) => [n.id, n])), [catalogNodes]);
  const categoryPath = product?.category_id ? buildPath(nodesById, product.category_id) : "";

  const normalizedLinks = useMemo(() => {
    const out: Record<string, string> = { restore: "", store77: "" };
    for (const l of content.links || []) {
      const host = parseHost(l.url || "");
      for (const site of AUTHORIZED_SITES) {
        if ((l.label || "").toLowerCase().includes(site.key) || site.hostIncludes.some((h) => host.includes(h))) {
          out[site.key] = l.url || "";
        }
      }
    }
    return out;
  }, [content.links]);

  const autoStatus = useMemo<ProductT["status"]>(() => {
    // Archived is explicit/manual only.
    if (status === "archived") return "archived";

    const hasTitle = !!String(title || "").trim();
    const hasMedia = Array.isArray(content.media_images) && content.media_images.length > 0;
    const hasDescription = !!String(content.description || "").trim();
    const hasDocs = Array.isArray(content.documents) && content.documents.length > 0;
    const hasPlatformLinks = AUTHORIZED_SITES.every((s) => !!String(normalizedLinks[s.key] || "").trim());

    const requiredDefs = (featureDefs || []).filter((d) => !!d.required);
    const requiredFilled = requiredDefs.every((d) => {
      const hit = (content.features || []).find((f) => qnorm(f.code || "") === qnorm(d.code));
      return !!String(hit?.value || "").trim();
    });

    const isComplete =
      hasTitle &&
      hasMedia &&
      hasDescription &&
      hasDocs &&
      hasPlatformLinks &&
      requiredFilled;

    return isComplete ? "active" : "draft";
  }, [status, title, content.media_images, content.description, content.documents, content.features, normalizedLinks, featureDefs]);

  const selectedVariantParamDefs = useMemo(() => {
    const selectedIds = new Set((groupVariantParams || []).filter((x) => x.selected).map((x) => x.id));
    return (groupVariantParams || []).filter((x) => selectedIds.has(x.id));
  }, [groupVariantParams]);

  const variantFilterOptions = useMemo(() => {
    const byKey: Record<string, string[]> = {};
    for (const def of selectedVariantParamDefs) {
      const values = new Set<string>();
      for (const it of groupItems) {
        const feats = groupItemFeatures[it.id] || [];
        const hit = feats.find(
          (f) =>
            (def.code && qnorm(f.code || "") === qnorm(def.code)) || qnorm(f.name || "") === qnorm(def.name || "")
        );
        if (hit?.value) values.add(hit.value);
      }
      byKey[def.id] = Array.from(values).sort((a, b) => a.localeCompare(b, "ru"));
    }
    return byKey;
  }, [selectedVariantParamDefs, groupItems, groupItemFeatures]);

  const filteredGroupItems = useMemo(() => {
    return (groupItems || []).filter((it) => {
      for (const def of selectedVariantParamDefs) {
        const selectedVal = groupFilterByParam[def.id] || "";
        if (!selectedVal) continue;
        const feats = groupItemFeatures[it.id] || [];
        const hit = feats.find(
          (f) =>
            (def.code && qnorm(f.code || "") === qnorm(def.code)) || qnorm(f.name || "") === qnorm(def.name || "")
        );
        if ((hit?.value || "") !== selectedVal) return false;
      }
      return true;
    });
  }, [groupItems, selectedVariantParamDefs, groupFilterByParam, groupItemFeatures]);

  const sortedFeatures = useMemo<DisplayFeatureRow[]>(() => {
    const rows: DisplayFeatureRow[] = [];
    const templateKeys = new Set<string>();
    const byCode = new Map((content.features || []).map((f) => [qnorm(f.code || ""), f]));
    const byName = new Map((content.features || []).map((f) => [qnorm(f.name || ""), f]));

    for (const def of featureDefs || []) {
      const key = qnorm(def.code || def.name);
      if (!key) continue;
      templateKeys.add(key);
      const hit = byCode.get(qnorm(def.code || "")) || byName.get(qnorm(def.name || ""));
      rows.push({
        key,
        code: String(def.code || "").trim(),
        name: String(def.name || def.code || "").trim(),
        value: String(hit?.value || ""),
        required: !!def.required,
        template: true,
      });
    }

    for (const item of content.features || []) {
      const key = qnorm(item.code || item.name);
      if (!key || templateKeys.has(key)) continue;
      rows.push({
        key,
        code: String(item.code || "").trim(),
        name: String(item.name || item.code || "").trim(),
        value: String(item.value || ""),
        required: false,
        template: false,
      });
    }

    return rows.sort((a, b) => a.name.localeCompare(b.name, "ru"));
  }, [content.features, featureDefs]);
  const descriptionStats = useMemo(() => {
    const text = String(content.description || "");
    const trimmed = text.trim();
    const words = trimmed ? trimmed.split(/\s+/).filter(Boolean).length : 0;
    return { chars: text.length, words };
  }, [content.description]);
  const descriptionPreviewHtml = useMemo(() => renderDescriptionHtml(content.description), [content.description]);
  const currentHeroImage = (content.media_images || [])[heroImageIndex] || null;
  const currentModalImage = imageModalIndex != null ? (content.media_images || [])[imageModalIndex] || null : null;

  const marketplaces = channelsSummary.marketplaces || [];
  const selectedMarketplace = openMarketplace
    ? marketplaces.find((item) => item.title === openMarketplace) || null
    : null;

  const modalItems = useMemo(() => {
    const q = qnorm(selectQuery);
    if (!selectModalKind) return [] as CatalogProductItem[];

    const selectedIds = new Set(
      (selectModalKind === "analogs" ? content.analogs : content.related)
        .map((x) => String(x.id || "").trim())
        .filter(Boolean)
    );

    return (allProducts || [])
      .filter((p) => p.id !== product?.id)
      .filter((p) => {
        if (!q) return true;
        return [toDisplayTitle(p), p.sku_gt || "", p.sku_id || "", buildPath(nodesById, p.category_id || "")]
          .join(" ")
          .toLowerCase()
          .includes(q);
      })
      .map((p) => ({ ...p, _selected: selectedIds.has(p.id) } as any));
  }, [selectModalKind, selectQuery, allProducts, content.analogs, content.related, product?.id, nodesById]);

  useEffect(() => {
    if (heroImageIndex > Math.max(0, (content.media_images || []).length - 1)) {
      setHeroImageIndex(0);
    }
  }, [content.media_images, heroImageIndex]);

  useEffect(() => {
    setSelectedImageIndexes((current) => current.filter((idx) => idx < (content.media_images || []).length));
  }, [content.media_images]);

  useEffect(() => {
    if (!productId) return;
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      setErr(null);
      try {
        const [prod, cats, productsList] = await Promise.all([
          api<ProductResp>(`/products/${encodeURIComponent(productId)}`),
          api<{ nodes: CatalogNode[] }>("/catalog/nodes"),
          api<{ items: CatalogProductItem[] }>("/catalog/products"),
        ]);

        if (cancelled) return;
        setProduct(prod.product);
        setCatalogNodes(cats.nodes || []);
        setAllProducts(productsList.items || []);
        try {
          const channels = await api<ChannelsSummaryResp>(`/products/${encodeURIComponent(productId)}/channels-summary`);
          if (!cancelled) {
            setChannelsSummary({
              marketplaces: channels.marketplaces?.length ? channels.marketplaces : defaultChannelsSummary().marketplaces,
              external_systems: channels.external_systems?.length ? channels.external_systems : defaultChannelsSummary().external_systems,
              competitors: channels.competitors?.length ? channels.competitors : defaultChannelsSummary().competitors,
            });
          }
        } catch {
          if (!cancelled) setChannelsSummary(defaultChannelsSummary());
        }

        setGroupName("");
        setGroupItems([]);
        setGroupVariantParams([]);
        setGroupFilterByParam({});
        setGroupItemFeatures({});
        setGroupItemPreviewUrls({});

        const gid = String(prod.product.group_id || "").trim();
        if (gid) {
          try {
            const [g, gp] = await Promise.all([
              api<GroupDetailsResp>(`/product-groups/${encodeURIComponent(gid)}`),
              api<VariantParamsResp>(`/product-groups/${encodeURIComponent(gid)}/variant-params`),
            ]);
            setGroupName(String(g.group?.name || ""));
            setGroupItems(g.items || []);

            const selected = new Set(gp.selected_ids || []);
            setGroupVariantParams((gp.items || []).map((x) => ({ ...x, selected: selected.has(x.id) })));

            const groupIds = (g.items || []).map((x) => String(x.id || "").trim()).filter(Boolean);
            const bulk = groupIds.length
              ? await api<{ items: ProductT[] }>(`/products/bulk?ids=${encodeURIComponent(groupIds.join(","))}`)
              : { items: [] };
            const productById = new Map((bulk.items || []).map((item) => [String(item.id || "").trim(), item]));
            const detailEntries = (g.items || []).map((x) => {
              const full = productById.get(String(x.id || "").trim());
              const feats = ((full?.content?.features as any[]) || []).map((f) => ({
                code: String(f?.code || ""),
                name: String(f?.name || ""),
                value: String(f?.value || ""),
              }));
              return [x.id, feats] as const;
            });
            const m: Record<string, ProductFeature[]> = {};
            const previews: Record<string, string> = {};
            for (const [pid, feats] of detailEntries) m[pid] = feats;
            for (const item of g.items || []) {
              const full = productById.get(String(item.id || "").trim());
              const rawContent = full?.content && typeof full.content === "object" ? full.content : {};
              const images = Array.isArray((rawContent as any).media_images) ? ((rawContent as any).media_images as any[]) : [];
              const firstImage = images.find((entry) => entry && typeof entry === "object" && String(entry.url || "").trim());
              if (firstImage?.url) previews[item.id] = String(firstImage.url);
            }
            if (cancelled) return;
            setGroupItemFeatures(m);
            setGroupItemPreviewUrls(previews);
          } catch {
            if (cancelled) return;
            setGroupName("");
            setGroupItems([]);
            setGroupVariantParams([]);
            setGroupFilterByParam({});
            setGroupItemFeatures({});
            setGroupItemPreviewUrls({});
          }
        }

        const nextTitle = prod.product.title || "";
        const nextStatus = prod.product.status || "draft";
        setTitle(nextTitle);
        setStatus(nextStatus);
        setSkuPim(prod.product.sku_pim || "");
        setSkuGt(prod.product.sku_gt || "");
        setSkuId(prod.product.sku_id || "");

        const merged = normalizeContent(prod.product.content || {});
        const normalizedRelations = (arr: ProductRelation[]) =>
          (arr || []).map((x) => ({
            id: String((x as any)?.id || "").trim() || undefined,
            name: String(x?.name || "").trim(),
            sku: String(x?.sku || "").trim(),
            sku_gt: String((x as any)?.sku_gt || "").trim() || undefined,
            sku_id: String((x as any)?.sku_id || "").trim() || undefined,
          }));

        merged.analogs = normalizedRelations(merged.analogs || []);
        merged.related = normalizedRelations(merged.related || []);
        setContent(merged);
        setSeoSourceA(String(merged.description || ""));
        setSeoSourceB("");
        setSeoKeywords("");
        setOriginalRelatedIds(merged.related.map((x) => String(x.id || "").trim()).filter(Boolean));

        try {
          const t = await api<TemplatesByCategoryResp>(`/templates/by-category/${encodeURIComponent(prod.product.category_id)}`);
          const attrs = (t.attributes || [])
            .filter((a) => isFeatureAttr(a))
            .map((a) => ({
              code: String(a.code || "").trim(),
              name: String(a.name || a.code || "").trim(),
              required: !!a.required,
            }))
            .filter((a) => a.code || a.name);
          if (cancelled) return;
          setFeatureDefs(attrs);

          const byCode = new Map((merged.features || []).map((f) => [qnorm(f.code || ""), f]));
          const byName = new Map((merged.features || []).map((f) => [qnorm(f.name || ""), f]));
          const nextFeatures: ProductFeature[] = attrs.map((d) => {
            const hit = byCode.get(qnorm(d.code)) || byName.get(qnorm(d.name));
            return { code: d.code, name: d.name, value: String(hit?.value || "") };
          });
          const known = new Set(nextFeatures.map((f) => qnorm(f.code || f.name)));
          for (const item of merged.features || []) {
            const key = qnorm(item.code || item.name);
            if (!key || known.has(key)) continue;
            nextFeatures.push({
              code: String(item.code || "").trim(),
              name: String(item.name || item.code || "").trim(),
              value: String(item.value || ""),
            });
          }
          if (cancelled) return;
          setContent((c) => mergeContent(c, { features: nextFeatures }));
        } catch {
          if (cancelled) return;
          setFeatureDefs([]);
        }
      } catch (e) {
        if (cancelled) return;
        setErr((e as Error).message || "Ошибка загрузки");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [productId]);

  const updateList = <T,>(list: T[], index: number, patch: Partial<T>) => {
    const next = list.slice();
    next[index] = { ...(next[index] as any), ...patch };
    return next;
  };

  const removeAt = <T,>(list: T[], index: number) => list.filter((_, i) => i !== index);

  function setAuthorizedLink(siteKey: "restore" | "store77", url: string) {
    const next = { ...normalizedLinks, [siteKey]: url };
    const links = AUTHORIZED_SITES.map((s) => ({ label: s.label, url: next[s.key] || "" }));
    setContent((c) => mergeContent(c, { links }));
  }

  function openCompetitorModal(siteKey: "restore" | "store77") {
    setCompetitorModalKey(siteKey);
    setCompetitorModalValue(normalizedLinks[siteKey] || "");
  }

  function saveCompetitorModal() {
    if (!competitorModalKey) return;
    setAuthorizedLink(competitorModalKey, competitorModalValue.trim());
    setChannelsSummary((prev) => ({
      ...prev,
      competitors: (prev.competitors || []).map((item) =>
        item.key === competitorModalKey
          ? { ...item, url: competitorModalValue.trim(), status: competitorModalValue.trim() ? "Подключен" : "Не задан" }
          : item
      ),
    }));
    setCompetitorModalKey(null);
    setCompetitorModalValue("");
  }

  function openVariantsSection() {
    setTab("variants");
    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        variantsSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }

  function setFeatureValue(feature: Pick<DisplayFeatureRow, "code" | "name">, value: string) {
    setContent((current) => {
      const list = (current.features || []).slice();
      const byCode = qnorm(feature.code || "");
      const byName = qnorm(feature.name || "");
      const index = list.findIndex(
        (item) => (byCode && qnorm(item.code || "") === byCode) || qnorm(item.name || "") === byName
      );
      if (index >= 0) {
        list[index] = { ...list[index], code: feature.code, name: feature.name, value };
      } else {
        list.push({ code: feature.code, name: feature.name, value });
      }
      return mergeContent(current, { features: list });
    });
  }

  function cycleHeroImage(direction: -1 | 1) {
    const count = (content.media_images || []).length;
    if (count < 2) return;
    setHeroImageIndex((current) => (current + direction + count) % count);
  }

  async function persistContent(nextContent: ProductContent) {
    setContent(nextContent);
    if (!productId) return;
    await api(`/products/${encodeURIComponent(productId)}`, {
      method: "PATCH",
      body: JSON.stringify({ content: nextContent }),
    });
  }

  async function confirmDeletePending() {
    if (!pendingDelete) return;
    if (pendingDelete.kind === "media_images_bulk") {
      for (const itemUrl of pendingDelete.urls || []) {
        if (itemUrl && String(itemUrl).startsWith("/api/uploads/")) {
          await api(`/products/uploads?url=${encodeURIComponent(itemUrl)}`, { method: "DELETE" });
        }
      }
      const indexes = new Set(pendingDelete.indexes || []);
      const next = (content.media_images || []).filter((_, idx) => !indexes.has(idx));
      const nextContent = normalizeContent({ ...content, media_images: next, media: next });
      await persistContent(nextContent);
      setSelectedImageIndexes([]);
      setPendingDelete(null);
      return;
    }
    const kind = pendingDelete.kind;
    const index = pendingDelete.index ?? -1;
    const url = pendingDelete.url;
    if (url && String(url).startsWith("/api/uploads/")) {
      await api(`/products/uploads?url=${encodeURIComponent(url)}`, { method: "DELETE" });
    }
    let nextContent: ProductContent = content;
    setContent((current) => {
      if (kind === "media_images") {
        const next = removeAt(current.media_images, index);
        nextContent = normalizeContent({ ...current, media_images: next, media: next });
        return nextContent;
      }
      if (kind === "media_videos") {
        nextContent = normalizeContent({ ...current, media_videos: removeAt(current.media_videos, index) });
        return nextContent;
      }
      if (kind === "media_cover") {
        nextContent = normalizeContent({ ...current, media_cover: removeAt(current.media_cover, index) });
        return nextContent;
      }
      nextContent = mergeContent(current, { documents: removeAt(current.documents, index) });
      return nextContent;
    });
    await persistContent(nextContent);
    if (kind === "media_images") {
      setSelectedImageIndexes((current) =>
        current
          .filter((item) => item !== index)
          .map((item) => (item > index ? item - 1 : item))
      );
    }
    setPendingDelete(null);
  }

  function toggleImageSelection(index: number) {
    setSelectedImageIndexes((current) =>
      current.includes(index) ? current.filter((item) => item !== index) : [...current, index].sort((a, b) => a - b)
    );
  }

  function toggleAllImages() {
    const total = (content.media_images || []).length;
    if (!total) return;
    if (selectedImageIndexes.length === total) {
      setSelectedImageIndexes([]);
      return;
    }
    setSelectedImageIndexes(Array.from({ length: total }, (_, idx) => idx));
  }

  async function uploadFiles(
    kind: "media_images" | "media_videos" | "media_cover" | "documents",
    files: FileList | null
  ) {
    if (!files?.length) return [] as Array<{ name: string; url: string; size?: number; content_type?: string }>;
    const form = new FormData();
    for (const f of Array.from(files)) form.append("files", f);
    const pid = encodeURIComponent(product?.id || "common");
    const url = `/api/products/uploads?kind=${encodeURIComponent(kind)}&product_id=${pid}`;
    const res = await fetch(url, { method: "POST", body: form });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(txt || "UPLOAD_FAILED");
    }
    const data = await res.json();
    return (data?.items || []) as Array<{ name: string; url: string; size?: number; content_type?: string }>;
  }

  async function appendImageFiles(files: FileList | null) {
    if (!files?.length) return;
    const images = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (!images.length) return;
    const dt = new DataTransfer();
    for (const f of images) dt.items.add(f);
    const uploaded = await uploadFiles("media_images", dt.files);
    const mapped = uploaded.map((x) => ({ url: x.url, caption: x.name }));
    const nextContent = normalizeContent({
      ...content,
      media_images: [...(content.media_images || []), ...mapped],
      media: [...(content.media_images || []), ...mapped],
    });
    await persistContent(nextContent);
  }

  async function appendVideoFiles(files: FileList | null) {
    if (!files?.length) return;
    const videos = Array.from(files).filter((f) => f.type.startsWith("video/"));
    if (!videos.length) return;
    const dt = new DataTransfer();
    for (const f of videos) dt.items.add(f);
    const uploaded = await uploadFiles("media_videos", dt.files);
    const mapped = uploaded.map((x) => ({ url: x.url, caption: x.name }));
    const nextContent = normalizeContent({ ...content, media_videos: [...(content.media_videos || []), ...mapped] });
    await persistContent(nextContent);
  }

  async function replaceVideoCover(files: FileList | null) {
    if (!files?.length) return;
    const videos = Array.from(files).filter((f) => f.type.startsWith("video/"));
    if (!videos.length) return;
    const dt = new DataTransfer();
    dt.items.add(videos[0]);
    const uploaded = await uploadFiles("media_cover", dt.files);
    const mapped = uploaded.map((x) => ({ url: x.url, caption: x.name }));
    const nextContent = normalizeContent({ ...content, media_cover: mapped.slice(0, 1) });
    await persistContent(nextContent);
  }

  async function appendDocumentFiles(files: FileList | null) {
    if (!files?.length) return;
    const uploaded = await uploadFiles("documents", files);
    const mapped = uploaded.map((x) => ({ name: x.name, url: x.url }));
    const nextContent = mergeContent(content, { documents: [...(content.documents || []), ...mapped] });
    await persistContent(nextContent);
  }

  async function syncReverseRelated(productCurrent: ProductT, relatedIdsNow: string[]) {
    const prev = new Set(originalRelatedIds);
    const now = new Set(relatedIdsNow);

    const toAdd = Array.from(now).filter((x) => !prev.has(x));
    const toRemove = Array.from(prev).filter((x) => !now.has(x));

    for (const targetId of [...toAdd, ...toRemove]) {
      try {
        const tgt = await api<{ product: ProductT }>(`/products/${encodeURIComponent(targetId)}?include_variants=false`);
        const tcontent = mergeContent(emptyContent, tgt.product.content || {});
        const arr = (tcontent.related || []).slice();
        const hasCurrent = arr.some((x) => String(x.id || "").trim() === productCurrent.id);

        let next = arr;
        if (toAdd.includes(targetId) && !hasCurrent) {
          next = [
            ...arr,
            {
              id: productCurrent.id,
              name: productCurrent.title || productCurrent.id,
              sku: productCurrent.sku_gt || productCurrent.sku_id || "",
              sku_gt: productCurrent.sku_gt || "",
              sku_id: productCurrent.sku_id || "",
            },
          ];
        }
        if (toRemove.includes(targetId)) {
          next = arr.filter((x) => String(x.id || "").trim() !== productCurrent.id);
        }

        if (next !== arr) {
          await api(`/products/${encodeURIComponent(targetId)}`, {
            method: "PATCH",
            body: JSON.stringify({ content: { related: next } }),
          });
        }
      } catch {
        // keep main save successful even if reverse sync failed for one item
      }
    }
  }

  const onSave = async () => {
    if (!productId || !product) return;
    setSaving(true);
    setErr(null);
    try {
      const linksSanitized = AUTHORIZED_SITES.map((s) => ({ label: s.label, url: normalizedLinks[s.key] || "" }));
      for (const l of linksSanitized) {
        const host = parseHost(l.url || "");
        if (l.url && !AUTHORIZED_SITES.find((s) => s.label === l.label)?.hostIncludes.some((h) => host.includes(h))) {
          throw new Error(`Ссылка ${l.label} должна вести на авторизованный сайт`);
        }
      }

      const featuresSanitized = featureDefs.map((d) => {
        const hit = (content.features || []).find((f) => qnorm(f.code || "") === qnorm(d.code));
        return {
          code: d.code,
          name: d.name,
          value: String(hit?.value || ""),
        };
      });
      const knownDefs = new Set(featureDefs.map((d) => qnorm(d.code)));
      const extraFeatures = (content.features || [])
        .filter((f) => !knownDefs.has(qnorm(f.code || "")))
        .filter((f) => String(f.value || "").trim())
        .map((f) => ({
          code: String(f.code || "").trim(),
          name: String(f.name || f.code || "").trim(),
          value: String(f.value || ""),
        }));

      const patch = {
        title,
        status: autoStatus,
        content: {
          ...content,
          media: content.media_images || [],
          links: linksSanitized,
          features: [...featuresSanitized, ...extraFeatures],
        },
      };

      const res = await api<{ product: ProductT }>(`/products/${encodeURIComponent(productId)}`, {
        method: "PATCH",
        body: JSON.stringify(patch),
      });

      setProduct(res.product);
      setStatus(res.product.status || autoStatus);
      setContent(normalizeContent({ ...content, links: linksSanitized, features: [...featuresSanitized, ...extraFeatures] }));

      const relatedIdsNow = (content.related || []).map((x) => String(x.id || "").trim()).filter(Boolean);
      await syncReverseRelated(res.product, relatedIdsNow);
      setOriginalRelatedIds(relatedIdsNow);
    } catch (e) {
      setErr((e as Error).message || "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  async function moveToArchive() {
    if (!productId || !product) return;
    const ok = window.confirm("Перевести товар в архив?");
    if (!ok) return;
    setSaving(true);
    setErr(null);
    try {
      const currentExports = (product.exports_enabled || {}) as Record<string, boolean>;
      const disabledExports: Record<string, boolean> = {};
      for (const key of Object.keys(currentExports)) disabledExports[key] = false;
      const res = await api<{ product: ProductT }>(`/products/${encodeURIComponent(productId)}`, {
        method: "PATCH",
        body: JSON.stringify({
          status: "archived",
          exports_enabled: disabledExports,
        }),
      });
      setProduct(res.product);
      setStatus("archived");
    } catch (e) {
      setErr((e as Error).message || "Ошибка перевода в архив");
    } finally {
      setSaving(false);
    }
  }

  async function generateSeoDescription() {
    const keywords = seoKeywords
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
    const requiredByCode = new Map((featureDefs || []).map((item) => [qnorm(item.code || item.name), !!item.required]));
    const featureFacts = (content.features || [])
      .filter((item) => String(item.value || "").trim())
      .map((item) => ({
        name: String(item.name || item.code || "").trim(),
        value: String(item.value || "").trim(),
        required: requiredByCode.get(qnorm(item.code || item.name)) || false,
      }));
    if (!seoSourceA.trim() && !seoSourceB.trim() && !(seoUseFeatures && featureFacts.length)) {
      setErr("Добавьте хотя бы один исходный текст для генерации.");
      return;
    }
    setSeoLoading(true);
    setErr(null);
    try {
      const r = await api<{ description: string; model?: string }>("/products/seo-description", {
        method: "POST",
        body: JSON.stringify({
          source_a: seoSourceA,
          source_b: seoSourceB,
          use_features: seoUseFeatures,
          features: featureFacts,
          keywords,
          profile: seoProfile,
          max_chars: 2200,
        }),
      });
      setContent((c) => mergeContent(c, { description: r.description || "" }));
    } catch (e) {
      setErr((e as Error).message || "Ошибка генерации описания");
    } finally {
      setSeoLoading(false);
    }
  }

  function toggleRelation(kind: "analogs" | "related", p: CatalogProductItem) {
    const key = kind;
    const current = (content[key] || []) as ProductRelation[];
    const exists = current.some((x) => String(x.id || "") === p.id);

    let next: ProductRelation[];
    if (exists) {
      next = current.filter((x) => String(x.id || "") !== p.id);
    } else {
      next = [
        ...current,
        {
          id: p.id,
          name: toDisplayTitle(p),
          sku: p.sku_gt || p.sku_id || "",
          sku_gt: p.sku_gt || "",
          sku_id: p.sku_id || "",
        },
      ];
    }

    setContent((c) => mergeContent(c, { [key]: next } as any));
  }

  if (loading) {
    return (
      <div className="pn-wrap pn-page">
        <div className="pn-card">Загрузка…</div>
      </div>
    );
  }

  if (!product) {
    return (
      <div className="pn-wrap pn-page">
        <div className="pn-card">Товар не найден.</div>
      </div>
    );
  }

  return (
    <div className="pn-wrap pn-page">
      <div className="pn-rightHeader">
        <div>
          <div className="pn-title">Товар</div>
          <div className="pn-sub">Полная карточка товара в стиле PIM</div>
        </div>

        <div className="pn-actions">
          <Link className="pn-editBtn" to="/catalog">
            ← Каталог
          </Link>
          <button className="pn-cancelBtn" type="button" onClick={moveToArchive} disabled={saving || status === "archived"}>
            В архив
          </button>
          <button className="pn-saveBtn" onClick={onSave} disabled={saving}>
            {saving ? <span className="pn-spinner" /> : <span className="pn-saveIcon">✓</span>}
            Сохранить
          </button>
        </div>
      </div>

      {err && (
        <div className="pn-card" ref={variantsSectionRef}>
          <div className="pn-alert pn-alertBad">
            <div className="pn-alertTitle">Ошибка</div>
            <div className="pn-alertText">{err}</div>
          </div>
        </div>
      )}

      <div className="pn-card pn-hero">
        <div className="pn-heroMedia">
          <div
            className={`pn-mediaMain ${currentHeroImage?.url ? "isInteractive" : ""}`}
            onClick={currentHeroImage?.url ? () => setImageModalIndex(heroImageIndex) : undefined}
          >
            {currentHeroImage?.url ? (
              <img src={toRenderableMediaUrl(currentHeroImage.url)} alt={currentHeroImage.caption || "media"} />
            ) : (
              <div className="pn-mediaPlaceholder">Нет изображений</div>
            )}
            {(content.media_images || []).length > 1 ? (
              <>
                <button
                  className="pn-heroGalleryNav isPrev"
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    cycleHeroImage(-1);
                  }}
                >
                  ‹
                </button>
                <button
                  className="pn-heroGalleryNav isNext"
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    cycleHeroImage(1);
                  }}
                >
                  ›
                </button>
              </>
            ) : null}
          </div>
          <div className="pn-mediaThumbs">
            {(content.media_images || []).slice(0, 5).map((m, idx) => (
              <button
                key={`${m.url}-${idx}`}
                type="button"
                className={`pn-mediaThumb ${idx === heroImageIndex ? "isActive" : ""}`}
                onClick={() => setHeroImageIndex(idx)}
                title={m.caption || `Фото ${idx + 1}`}
              >
                <img src={toRenderableMediaUrl(m.url)} alt={m.caption || `Фото ${idx + 1}`} />
              </button>
            ))}
          </div>
          <label className="pn-dropLite">
            <input
              type="file"
              multiple
              accept="image/*"
              style={{ display: "none" }}
              onChange={async (e) => {
                await appendImageFiles(e.target.files);
                e.currentTarget.value = "";
              }}
            />
            Перетащите или выберите изображения
          </label>
        </div>

        <div className="pn-heroMain">
          <div className="pn-heroTopLine">
            <span className={`pn-badge pn-badge-${autoStatus}`}>{autoStatus === "draft" ? "черновик" : autoStatus === "active" ? "активный" : "архив"}</span>
          </div>
          <div className="pn-heroCategory">{categoryPath || "—"}</div>
          <input className="pn-heroTitleInput" value={title} onChange={(e) => setTitle(e.target.value)} />
          <div className="pn-heroSkuLine">
            GT ID: {skuGt || "-"} · IDs ID: {skuId || "-"} · PIM ID: {skuPim || "-"}{" "}
            <span className="pn-heroSkuPipe">|</span> Группа товара:{" "}
            {product.group_id ? (
              <button className="pn-inlineLinkBtn" type="button" onClick={openVariantsSection}>
                {groupName || product.group_id}
              </button>
            ) : (
              "Без группы"
            )}
          </div>

          <div className="pn-heroMetaGrid">
            <div className="pn-field pn-fieldWide">
              <div className="pn-label">Площадки</div>
              <div className="pn-channelShell">
                <div className="pn-channelSectionHead">
                  <div className="pn-channelSectionTitle">Маркетплейсы</div>
                  <div className="pn-channelSectionHint">Статус и рейтинг по каждому магазину</div>
                </div>
                <div className="pn-marketSelectorRow">
                  {marketplaces.map((item) => (
                    <button
                      key={item.title}
                      className={`pn-marketSelectorCard ${selectedMarketplace?.title === item.title ? "isActive" : ""}`}
                      type="button"
                      onClick={() => setOpenMarketplace((cur) => (cur === item.title ? "" : item.title))}
                    >
                        <div className="pn-marketIdentity">
                          <div className="pn-marketTitleRow">
                            <span className="pn-marketStatusDotWrap" title={statusDotLabel(item.status)} aria-label={statusDotLabel(item.status)}>
                              <span className={`pn-statusDot lg is-${marketplaceOverviewTone(item)}`} />
                            </span>
                            <div className="pn-marketTitleBlock">
                              <div className="pn-channelName">{item.title}</div>
                              <div className="pn-marketStoreCount">{marketplaceStoreCountLabel(item)}</div>
                            </div>
                          </div>
                        </div>
                      <div className="pn-marketHeadRight">
                        <div className="pn-scoreChip" style={ratingStyle(item.content_rating)}>
                          <span className="pn-scoreChipValue">{item.stores?.length ? item.content_rating : "-"}</span>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
                {selectedMarketplace ? (
                  <div className="pn-marketDetailPanel">
                    {!!selectedMarketplace.stores?.length ? (
                      <div className="pn-storeList">
                        {selectedMarketplace.stores.map((store) => (
                          <div key={store.store_id} className="pn-storeRow">
                            <div className="pn-storeRowMain">
                              <div className="pn-storeRowTitle">{store.store_title}</div>
                              <div className={`pn-storeRowStatus is-${channelTone(store.status)}`}>{displayChannelStatus(store.status)}</div>
                            </div>
                            <div className="pn-storeRowSide">
                              <div className="pn-storeScoreMini" style={ratingStyle(store.content_rating)}>
                                {store.content_rating ?? "Нет данных"}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="pn-marketEmpty">Магазины не подключены или по товару еще не было синхронизации.</div>
                    )}
                  </div>
                ) : null}
                <div className="pn-channelSectionHead">
                  <div className="pn-channelSectionTitle">Внешние системы</div>
                </div>
                <div className="pn-channelAuxGrid">
                  {(channelsSummary.external_systems || []).map((item) => (
                    <div key={item.title} className="pn-auxCard pn-auxCardCompact">
                      <div className="pn-channelMeta">
                        <div className="pn-channelName">{item.title}</div>
                        <div className="pn-channelSub">{item.status}</div>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="pn-channelSectionHead">
                  <div className="pn-channelSectionTitle">Конкуренты</div>
                </div>
                <div className="pn-channelAuxGrid">
                  {(channelsSummary.competitors || []).map((item) => (
                    <div key={item.key} className="pn-auxCard pn-auxCardCompact pn-auxCardWithAction">
                      <div className="pn-channelMeta pn-auxCardMeta">
                        <div className="pn-competitorHead">
                          <div className="pn-competitorTitleBlock">
                            <div className="pn-channelName">{item.title}</div>
                            <div className="pn-competitorStatus">{displayChannelStatus(item.status)}</div>
                          </div>
                          {item.url ? (
                            <a className="pn-linkIcon" href={item.url} target="_blank" rel="noreferrer" title="Открыть ссылку">
                              ↗
                            </a>
                          ) : null}
                        </div>
                      </div>
                      <button
                        className={`pn-editBtn pn-linkBtn ${item.url ? "isLinked" : "isEmpty"}`}
                        type="button"
                        onClick={() => openCompetitorModal(item.key)}
                      >
                        Ссылка
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="pn-card">
        <div className="pn-tabs pn-tabsUnder">
          <button className={`pn-tab ${tab === "variants" ? "isActive" : ""}`} onClick={() => setTab("variants")} type="button">
            Варианты
          </button>
          <button className={`pn-tab ${tab === "media" ? "isActive" : ""}`} onClick={() => setTab("media")} type="button">
            Медиа
          </button>
          <button className={`pn-tab ${tab === "features" ? "isActive" : ""}`} onClick={() => setTab("features")} type="button">
            Характеристики
          </button>
          <button className={`pn-tab ${tab === "description" ? "isActive" : ""}`} onClick={() => setTab("description")} type="button">
            Описание
          </button>
          <button className={`pn-tab ${tab === "documents" ? "isActive" : ""}`} onClick={() => setTab("documents")} type="button">
            Документы
          </button>
          <button className={`pn-tab ${tab === "analogs" ? "isActive" : ""}`} onClick={() => setTab("analogs")} type="button">
            Аналоги
          </button>
          <button className={`pn-tab ${tab === "related" ? "isActive" : ""}`} onClick={() => setTab("related")} type="button">
            Сопутствующие
          </button>
        </div>
      </div>

      {tab === "variants" && (
        <div className="pn-card">
          <div className="pn-variantSection">
            <div className="pn-cardTitle">Варианты</div>

            {groupItems.length > 0 && (
              <>
              <div className="pn-muted pn-variantLead">
                Группа товара:{" "}
                {product.group_id ? (
                  <Link to={`/catalog/groups?group=${encodeURIComponent(product.group_id)}`} style={{ textDecoration: "underline" }}>
                    {groupName || product.group_id}
                  </Link>
                ) : (
                  "-"
                )}
              </div>

              {selectedVariantParamDefs.length > 0 && (
                <div className="pn-list pn-variantFilters">
                  <div className="pn-listRow pn-variantFiltersGrid">
                    {selectedVariantParamDefs.map((def) => (
                      <div key={def.id}>
                        <div className="pn-label" style={{ marginBottom: 4 }}>
                          {def.name}
                        </div>
                        <select
                          className="pn-input"
                          value={groupFilterByParam[def.id] || ""}
                          onChange={(e) => setGroupFilterByParam((prev) => ({ ...prev, [def.id]: e.target.value }))}
                        >
                          <option value="">Все</option>
                          {(variantFilterOptions[def.id] || []).map((v) => (
                            <option key={v} value={v}>
                              {v}
                            </option>
                          ))}
                        </select>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="pn-variantList pn-variantTable">
                <div className="pn-variantRow pn-variantHead" style={{ gridTemplateColumns: "260px 1fr 88px" }}>
                  <div>Артикулы</div>
                  <div>Наименование</div>
                  <div />
                </div>
                {filteredGroupItems.map((it) => {
                  const isCurrent = it.id === product.id;
                  return (
                    <div
                      key={it.id}
                      className={`pn-variantRow ${!isCurrent ? "pn-variantRowClickable" : ""} ${isCurrent ? "isCurrent" : ""}`}
                      style={{ gridTemplateColumns: "260px 1fr 88px" }}
                      role={isCurrent ? undefined : "link"}
                      tabIndex={isCurrent ? -1 : 0}
                      onClick={isCurrent ? undefined : () => navigate(`/products/${encodeURIComponent(it.id)}`)}
                      onKeyDown={
                        isCurrent
                          ? undefined
                          : (e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                navigate(`/products/${encodeURIComponent(it.id)}`);
                              }
                            }
                      }
                    >
                      <div className="pn-variantSkuCell">
                        {groupItemPreviewUrls[it.id] ? (
                          <div className="pn-variantPreview">
                            <img src={toRenderableMediaUrl(groupItemPreviewUrls[it.id])} alt={toDisplayTitle(it)} />
                          </div>
                        ) : (
                          <div className="pn-variantPreview isEmpty">Нет фото</div>
                        )}
                        <div className="pn-muted">{toSkuLine(it)}</div>
                      </div>
                      <div className="pn-variantTitleCell" style={{ fontWeight: 700 }}>{toDisplayTitle(it)}</div>
                      {isCurrent ? (
                        <span className="pn-chip">Текущий</span>
                      ) : (
                        <Link
                          className="pn-editBtn"
                          to={`/products/${encodeURIComponent(it.id)}`}
                          onClick={(e) => e.stopPropagation()}
                        >
                          Открыть
                        </Link>
                      )}
                    </div>
                  );
                })}
                {!filteredGroupItems.length && <div className="pn-muted">По фильтрам ничего не найдено.</div>}
              </div>
              </>
            )}

            {!groupItems.length && <div className="pn-muted">Вариантов нет.</div>}
          </div>
        </div>
      )}

      {tab === "media" && (
        <div className="pn-card">
          <div className="pn-cardTitle">Медиа</div>
          <div className="pn-mediaSections">
            <div className="pn-mediaSection">
              <div className="pn-mediaSectionHead">
                <div className="pn-cardSubTitle">Картинки</div>
              </div>
              <div className="pn-mediaSectionBody">
                <div
                  className="pn-mediaDropZone"
                  onDragOver={(e: DragEvent) => e.preventDefault()}
                  onDrop={async (e: DragEvent) => {
                    e.preventDefault();
                    await appendImageFiles(e.dataTransfer.files);
                  }}
                >
                  <div className="pn-mediaDropText">Перетащите изображения сюда или выберите файлы</div>
                  <div className="pn-mediaDropActions">
                    <label className="pn-editBtn" style={{ cursor: "pointer" }}>
                      Выбрать файлы
                      <input
                        type="file"
                        multiple
                        accept="image/*"
                        style={{ display: "none" }}
                        onChange={async (e) => {
                          await appendImageFiles(e.target.files);
                          e.currentTarget.value = "";
                        }}
                      />
                    </label>
                  </div>
                </div>
                {(content.media_images || []).length > 0 && (
                  <div className="pn-imageGalleryToolbar">
                    <label className="pn-imageGallerySelectAll">
                      <input
                        type="checkbox"
                        checked={(content.media_images || []).length > 0 && selectedImageIndexes.length === (content.media_images || []).length}
                        onChange={toggleAllImages}
                      />
                      <span>Выбрать все</span>
                    </label>
                    <div className="pn-imageGalleryToolbarActions">
                      <span className="pn-muted">
                        {selectedImageIndexes.length ? `Выбрано: ${selectedImageIndexes.length}` : "Ничего не выбрано"}
                      </span>
                      <button
                        className="pn-cancelBtn"
                        type="button"
                        disabled={!selectedImageIndexes.length}
                        onClick={() =>
                          setPendingDelete({
                            kind: "media_images_bulk",
                            indexes: selectedImageIndexes,
                            urls: selectedImageIndexes.map((itemIdx) => content.media_images[itemIdx]?.url).filter(Boolean) as string[],
                          })
                        }
                      >
                        Удалить выбранные
                      </button>
                    </div>
                  </div>
                )}
                <div className="pn-imageGallery">
                  {(content.media_images || []).map((m, idx) => (
                    <div key={`media-image-${idx}`} className={`pn-imageCard${selectedImageIndexes.includes(idx) ? " isSelected" : ""}`}>
                      <label className="pn-imageCardCheck">
                        <input
                          type="checkbox"
                          checked={selectedImageIndexes.includes(idx)}
                          onChange={() => toggleImageSelection(idx)}
                        />
                      </label>
                      <button
                        className="pn-imageCardDelete"
                        type="button"
                        aria-label="Удалить изображение"
                        onClick={() => setPendingDelete({ kind: "media_images", index: idx, url: m.url })}
                      >
                        ×
                      </button>
                      <button className="pn-imageCardPreview" type="button" onClick={() => setImageModalIndex(idx)}>
                        {m.url ? <img src={toRenderableMediaUrl(m.url)} alt={m.caption || `Изображение ${idx + 1}`} /> : <span>Нет</span>}
                      </button>
                      <input
                        className="pn-input pn-imageCardCaption"
                        placeholder="Подпись"
                        value={m.caption || ""}
                        onChange={(e) =>
                          setContent((c) =>
                            normalizeContent({
                              ...c,
                              media_images: updateList(c.media_images, idx, { caption: e.target.value }),
                              media: updateList(c.media_images, idx, { caption: e.target.value }),
                            })
                          )
                        }
                        onBlur={async (e) => {
                          const nextContent = normalizeContent({
                            ...content,
                            media_images: updateList(content.media_images, idx, { caption: e.target.value }),
                            media: updateList(content.media_images, idx, { caption: e.target.value }),
                          });
                          await persistContent(nextContent);
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="pn-mediaSection">
              <div className="pn-mediaSectionHead">
                <div className="pn-cardSubTitle">Видео</div>
              </div>
              <div className="pn-mediaSectionBody">
                <div
                  className="pn-mediaDropZone"
                  onDragOver={(e: DragEvent) => e.preventDefault()}
                  onDrop={async (e: DragEvent) => {
                    e.preventDefault();
                    await appendVideoFiles(e.dataTransfer.files);
                  }}
                >
                  <div className="pn-mediaDropText">Перетащите видео сюда или выберите файлы</div>
                  <div className="pn-mediaDropActions">
                    <label className="pn-editBtn" style={{ cursor: "pointer" }}>
                      Выбрать файлы
                      <input
                        type="file"
                        multiple
                        accept="video/*"
                        style={{ display: "none" }}
                        onChange={async (e) => {
                          await appendVideoFiles(e.target.files);
                          e.currentTarget.value = "";
                        }}
                      />
                    </label>
                  </div>
                </div>
                <div className="pn-list">
                  {(content.media_videos || []).map((m, idx) => (
                    <div key={`media-video-${idx}`} className="pn-listRow pn-mediaRow pn-mediaRowSimple">
                      <div className="pn-mediaRowPreview">
                        {m.url ? <video src={toRenderableMediaUrl(m.url)} muted playsInline preload="metadata" /> : <span>Нет</span>}
                      </div>
                      <div className="pn-mediaMetaStack">
                        <input
                          className="pn-input"
                          placeholder="Подпись"
                          value={m.caption || ""}
                          onChange={(e) =>
                            setContent((c) =>
                              normalizeContent({ ...c, media_videos: updateList(c.media_videos, idx, { caption: e.target.value }) })
                            )
                          }
                          onBlur={async (e) => {
                            const nextContent = normalizeContent({
                              ...content,
                              media_videos: updateList(content.media_videos, idx, { caption: e.target.value }),
                            });
                            await persistContent(nextContent);
                          }}
                        />
                        <div className="pn-mediaMetaUrl">{m.url}</div>
                      </div>
                      <div className="pn-mediaRowActions">
                        <button
                          className="pn-editBtn"
                          type="button"
                          onClick={() => {
                            setVideoModalUrl(m.url || "");
                            setVideoModalTitle(m.caption || `Видео ${idx + 1}`);
                          }}
                        >
                          Смотреть
                        </button>
                        <button className="pn-cancelBtn" type="button" onClick={() => setPendingDelete({ kind: "media_videos", index: idx, url: m.url })}>
                          Удалить
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="pn-mediaSection">
              <div className="pn-mediaSectionHead">
                <div className="pn-cardSubTitle">Видеообложка</div>
              </div>
              <div className="pn-mediaSectionBody">
                <div
                  className="pn-mediaDropZone"
                  onDragOver={(e: DragEvent) => e.preventDefault()}
                  onDrop={async (e: DragEvent) => {
                    e.preventDefault();
                    await replaceVideoCover(e.dataTransfer.files);
                  }}
                >
                  <div className="pn-mediaDropText">Перетащите вертикальное видео сюда или выберите файл</div>
                  <div className="pn-mediaDropActions">
                    <label className="pn-editBtn" style={{ cursor: "pointer" }}>
                      Выбрать файл
                      <input
                        type="file"
                        accept="video/*"
                        style={{ display: "none" }}
                        onChange={async (e) => {
                          await replaceVideoCover(e.target.files);
                          e.currentTarget.value = "";
                        }}
                      />
                    </label>
                  </div>
                </div>
                <div className="pn-list">
                  {(content.media_cover || []).map((m, idx) => (
                    <div key={`media-cover-${idx}`} className="pn-listRow pn-mediaRow pn-mediaRowSimple">
                      <div className="pn-mediaRowPreview isVertical">
                        {m.url ? <video src={toRenderableMediaUrl(m.url)} muted playsInline preload="metadata" /> : <span>Нет</span>}
                      </div>
                      <div className="pn-mediaMetaStack">
                        <input
                          className="pn-input"
                          placeholder="Подпись"
                          value={m.caption || ""}
                          onChange={(e) =>
                            setContent((c) =>
                              normalizeContent({ ...c, media_cover: updateList(c.media_cover, idx, { caption: e.target.value }) })
                            )
                          }
                          onBlur={async (e) => {
                            const nextContent = normalizeContent({
                              ...content,
                              media_cover: updateList(content.media_cover, idx, { caption: e.target.value }),
                            });
                            await persistContent(nextContent);
                          }}
                        />
                        <div className="pn-mediaMetaUrl">{m.url}</div>
                      </div>
                      <div className="pn-mediaRowActions">
                        <button
                          className="pn-editBtn"
                          type="button"
                          onClick={() => {
                            setVideoModalUrl(m.url || "");
                            setVideoModalTitle(m.caption || "Видеообложка");
                          }}
                        >
                          Смотреть
                        </button>
                        <button className="pn-cancelBtn" type="button" onClick={() => setPendingDelete({ kind: "media_cover", index: idx, url: m.url })}>
                          Удалить
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {tab === "features" && (
        <div className="pn-card">
          <div className="pn-sectionHeader">
            <div>
              <div className="pn-cardTitle">Характеристики</div>
              <div className="pn-muted">Поля берутся только из мастер-шаблона категории.</div>
            </div>
          </div>
          <div className="pn-featureTable">
            {sortedFeatures.map((f) => (
              <div key={f.key} className={`pn-featureRow${String(f.value || "").trim() ? "" : " isEmpty"}`}>
                <div className="pn-featureName">
                  {f.name}
                  {f.required ? <span className="pn-featureRequired">*</span> : null}
                </div>
                <div className="pn-featureInputWrap">
                  <input
                    className="pn-input pn-featureInput"
                    placeholder="Не заполнено"
                    value={f.value}
                    onChange={(e) => setFeatureValue(f, e.target.value)}
                  />
                  {!String(f.value || "").trim() ? <span className="pn-featureEmptyTag">Пусто</span> : null}
                </div>
              </div>
            ))}
            {!featureDefs.length && !content.features.length && <div className="pn-muted">Для категории не найден мастер-шаблон.</div>}
          </div>
        </div>
      )}

      {tab === "description" && (
        <div className="pn-card">
          <div className="pn-sectionHeader">
            <div>
              <div className="pn-cardTitle">Описание</div>
              <div className="pn-muted">
                Подтягивается из загруженных данных или генерируется AI на основе двух описаний и ключевых слов.
              </div>
            </div>
          </div>

          <div className="pn-descriptionShell">
            <div className="pn-descriptionWorkspace">
              <div className="pn-descriptionMain">
                <div className="pn-descriptionResult">
                  <div className="pn-descriptionResultHead">
                    <div>
                      <div className="pn-label pn-descriptionSourceLabel">Итоговое описание</div>
                      <div className="pn-muted">Основной текст карточки товара.</div>
                    </div>
                    <div className="pn-descriptionResultHeadRight">
                      <div className="pn-descriptionStats">
                        <span>{descriptionStats.words} слов</span>
                        <span>{descriptionStats.chars} символов</span>
                      </div>
                      <div className="pn-descriptionViewSwitch">
                        <button
                          className={`pn-tab pn-descriptionViewBtn${descriptionView === "preview" ? " isActive" : ""}`}
                          type="button"
                          onClick={() => setDescriptionView("preview")}
                        >
                          Превью
                        </button>
                        <button
                          className={`pn-tab pn-descriptionViewBtn${descriptionView === "edit" ? " isActive" : ""}`}
                          type="button"
                          onClick={() => setDescriptionView("edit")}
                        >
                          HTML
                        </button>
                      </div>
                    </div>
                  </div>
                  {descriptionView === "preview" ? (
                    <div
                      className="pn-descriptionPreview"
                      dangerouslySetInnerHTML={{ __html: descriptionPreviewHtml || "<p>Описание из загруженных данных…</p>" }}
                    />
                  ) : (
                    <textarea
                      className="pn-textarea pn-descriptionResultArea"
                      placeholder="Описание из загруженных данных…"
                      value={content.description}
                      onChange={(e) => setContent((c) => mergeContent(c, { description: e.target.value }))}
                    />
                  )}
                </div>
              </div>

              <aside className="pn-descriptionSidebar">
                <div className="pn-descriptionSidebarCard">
                  <div className="pn-label pn-descriptionSourceLabel">Ключевые слова</div>
                  <input
                    className="pn-input pn-descriptionKeywords"
                    placeholder="смартфон 5G, AMOLED, NFC..."
                    value={seoKeywords}
                    onChange={(e) => setSeoKeywords(e.target.value)}
                  />
                </div>

                <div className="pn-descriptionSidebarCard">
                  <div className="pn-label pn-descriptionSourceLabel">Режим генерации</div>
                  <label className="pn-descriptionCheckbox">
                    <input
                      type="checkbox"
                      checked={seoUseFeatures}
                      onChange={(e) => setSeoUseFeatures(e.target.checked)}
                    />
                    <span>На основе характеристик</span>
                  </label>
                  <div className="pn-descriptionHint">
                    AI возьмет заполненные характеристики как основу фактов и органично встроит их в SEO-описание.
                  </div>
                  <div className="pn-descriptionControlActions">
                    <div className="pn-selectWrap pn-descriptionProfileWrap">
                      <select
                        className="pn-select"
                        value={seoProfile}
                        onChange={(e) => setSeoProfile(e.target.value as any)}
                      >
                        <option value="fast">Быстро</option>
                        <option value="balanced">Баланс</option>
                        <option value="quality">Качество</option>
                      </select>
                      <div className="pn-caret">▾</div>
                    </div>
                    <button className="pn-editBtn" type="button" disabled={seoLoading} onClick={generateSeoDescription}>
                      {seoLoading ? "Генерирую..." : "AI SEO-описание"}
                    </button>
                  </div>
                </div>

                <div className="pn-descriptionSidebarCard">
                  <div className="pn-label pn-descriptionSourceLabel">Источник 1</div>
                  <textarea
                    className="pn-textarea pn-descriptionSourceArea"
                    placeholder="Вставьте первое описание..."
                    value={seoSourceA}
                    onChange={(e) => setSeoSourceA(e.target.value)}
                  />
                </div>

                <div className="pn-descriptionSidebarCard">
                  <div className="pn-label pn-descriptionSourceLabel">Источник 2</div>
                  <textarea
                    className="pn-textarea pn-descriptionSourceArea"
                    placeholder="Вставьте второе описание..."
                    value={seoSourceB}
                    onChange={(e) => setSeoSourceB(e.target.value)}
                  />
                </div>
              </aside>
            </div>
          </div>
        </div>
      )}

      {tab === "documents" && (
        <div className="pn-card">
          <div className="pn-cardTitle">Документы</div>
          <div
            className="pn-mediaDropZone"
            onDragOver={(e: DragEvent) => {
              e.preventDefault();
            }}
            onDrop={async (e: DragEvent) => {
              e.preventDefault();
              await appendDocumentFiles(e.dataTransfer.files);
            }}
          >
            <div className="pn-mediaDropText">Перетащите документы сюда или выберите файлы</div>
            <div className="pn-mediaDropActions">
              <label className="pn-editBtn" style={{ cursor: "pointer" }}>
                Выбрать файлы
                <input
                  type="file"
                  multiple
                  style={{ display: "none" }}
                  onChange={async (e) => {
                    await appendDocumentFiles(e.target.files);
                    e.currentTarget.value = "";
                  }}
                />
              </label>
            </div>
          </div>

          <div className="pn-list pn-docList">
            {content.documents.map((d, idx) => (
              <div key={`doc-${idx}`} className="pn-listRow pn-docRow">
                <div className="pn-docMeta">
                  <input
                    className="pn-input"
                    placeholder="Название"
                    value={d.name}
                    onChange={(e) =>
                      setContent((c) => mergeContent(c, { documents: updateList(c.documents, idx, { name: e.target.value }) }))
                    }
                  />
                  <div className="pn-mediaMetaUrl">{d.url}</div>
                </div>
                <div className="pn-docActions">
                  <a className="pn-editBtn" href={toRenderableMediaUrl(d.url)} target="_blank" rel="noreferrer">
                    Открыть
                  </a>
                  <button className="pn-cancelBtn" type="button" onClick={() => setPendingDelete({ kind: "documents", index: idx, url: d.url })}>Удалить</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === "analogs" && (
        <div className="pn-card">
          <div className="pn-sectionHeader">
            <div>
              <div className="pn-cardTitle">Аналоги</div>
              <div className="pn-muted">Товары со схожим назначением или близкими характеристиками.</div>
            </div>
          </div>
          <div className="pn-relList">
            {(content.analogs || []).map((a, idx) => (
              <div key={`${a.id || a.sku || "a"}-${idx}`} className="pn-relCard">
                <div className="pn-relMetaBlock">
                  <div className="pn-relName">{a.name || a.id || "Товар"}</div>
                  <div className="pn-relMeta">GT: {a.sku_gt || "-"} | IDS: {a.sku_id || "-"}</div>
                </div>
                <div className="pn-relActions">
                  {a.id ? <Link className="pn-editBtn" to={`/products/${encodeURIComponent(a.id)}`}>Открыть</Link> : <span />}
                  <button className="pn-cancelBtn" type="button" onClick={() => setContent((c) => mergeContent(c, { analogs: removeAt(c.analogs, idx) }))}>Удалить</button>
                </div>
              </div>
            ))}
            {!content.analogs.length && <div className="pn-muted">Список аналогов пуст.</div>}
          </div>
          <div className="pn-footerActions pn-footerActionsStart">
            <button className="pn-editBtn" type="button" onClick={() => setSelectModalKind("analogs")}>+ Добавить из каталога</button>
          </div>
        </div>
      )}

      {tab === "related" && (
        <div className="pn-card">
          <div className="pn-sectionHeader">
            <div>
              <div className="pn-cardTitle">Сопутствующие</div>
              <div className="pn-muted">Обратная совместимость: связь синхронизируется в обе стороны при сохранении.</div>
            </div>
          </div>
          <div className="pn-relList">
            {(content.related || []).map((r, idx) => (
              <div key={`${r.id || r.sku || "r"}-${idx}`} className="pn-relCard">
                <div className="pn-relMetaBlock">
                  <div className="pn-relName">{r.name || r.id || "Товар"}</div>
                  <div className="pn-relMeta">GT: {r.sku_gt || "-"} | IDS: {r.sku_id || "-"}</div>
                </div>
                <div className="pn-relActions">
                  {r.id ? <Link className="pn-editBtn" to={`/products/${encodeURIComponent(r.id)}`}>Открыть</Link> : <span />}
                  <button className="pn-cancelBtn" type="button" onClick={() => setContent((c) => mergeContent(c, { related: removeAt(c.related, idx) }))}>Удалить</button>
                </div>
              </div>
            ))}
            {!content.related.length && <div className="pn-muted">Список сопутствующих пуст.</div>}
          </div>
          <div className="pn-footerActions pn-footerActionsStart">
            <button className="pn-editBtn" type="button" onClick={() => setSelectModalKind("related")}>+ Добавить из каталога</button>
          </div>
        </div>
      )}

      {selectModalKind && (
        <div className="pg-modalBackdrop" onClick={() => setSelectModalKind(null)}>
          <div className="pg-modal pg-modalWide" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">{selectModalKind === "analogs" ? "Добавить аналоги" : "Добавить сопутствующие"}</div>
                <div className="muted">Выберите товары. Зеленая галочка означает, что товар уже выбран.</div>
              </div>
              <button className="btn" type="button" onClick={() => setSelectModalKind(null)}>Закрыть</button>
            </div>

            <div className="pg-modalBody">
              <input
                className="pn-input"
                placeholder="Поиск по товарам, артикулам и категории…"
                value={selectQuery}
                onChange={(e) => setSelectQuery(e.target.value)}
              />
              <div className="pg-addList" style={{ marginTop: 10, maxHeight: "56vh" }}>
                {modalItems.map((p: any) => (
                  <button
                    key={p.id}
                    type="button"
                    className="pg-itemRow"
                    style={{ width: "100%", textAlign: "left", justifyContent: "space-between" }}
                    onClick={() => toggleRelation(selectModalKind, p)}
                  >
                    <div>
                      <div style={{ fontWeight: 700 }}>{toDisplayTitle(p)}</div>
                      <div className="muted">{toSkuLine(p)}</div>
                      <div className="muted">{buildPath(nodesById, p.category_id || "")}</div>
                    </div>
                    <div style={{ fontSize: 18, color: p._selected ? "#16a34a" : "#9ca3af" }}>{p._selected ? "✓" : "○"}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {videoModalUrl && (
        <div className="pg-modalBackdrop" onClick={() => setVideoModalUrl("")}>
          <div className="pg-modal pg-modalWide pn-mediaModal" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">{videoModalTitle || "Просмотр видео"}</div>
                <div className="muted">Просмотр файла в полном размере.</div>
              </div>
              <button className="btn" type="button" onClick={() => setVideoModalUrl("")}>Закрыть</button>
            </div>
            <div className="pg-modalBody pn-mediaModalBody">
              <video
                src={toRenderableMediaUrl(videoModalUrl)}
                controls
                autoPlay
                playsInline
                style={{ width: "100%", maxHeight: "72vh", borderRadius: 16, background: "#f8fafc" }}
              />
            </div>
          </div>
        </div>
      )}

      {imageModalIndex != null && currentModalImage?.url && (
        <div className="pg-modalBackdrop" onClick={() => setImageModalIndex(null)}>
          <div className="pg-modal pg-modalWide pn-imageLightbox" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">{currentModalImage.caption || `Изображение ${imageModalIndex + 1}`}</div>
                <div className="muted">{`${imageModalIndex + 1} из ${(content.media_images || []).length}`}</div>
              </div>
              <button className="btn" type="button" onClick={() => setImageModalIndex(null)}>Закрыть</button>
            </div>
            <div className="pg-modalBody pn-imageLightboxBody">
              {(content.media_images || []).length > 1 ? (
                <button className="pn-lightboxNav isPrev" type="button" onClick={() => setImageModalIndex((imageModalIndex - 1 + content.media_images.length) % content.media_images.length)}>
                  ‹
                </button>
              ) : null}
              <img
                className="pn-imageLightboxImg"
                src={toRenderableMediaUrl(content.media_images[imageModalIndex].url)}
                alt={content.media_images[imageModalIndex].caption || `Изображение ${imageModalIndex + 1}`}
              />
              {(content.media_images || []).length > 1 ? (
                <button className="pn-lightboxNav isNext" type="button" onClick={() => setImageModalIndex((imageModalIndex + 1) % content.media_images.length)}>
                  ›
                </button>
              ) : null}
            </div>
            {(content.media_images || []).length > 1 ? (
              <div className="pn-imageLightboxStrip">
                {(content.media_images || []).map((item, idx) => (
                  <button
                    key={`lightbox-thumb-${idx}`}
                    className={`pn-imageLightboxThumb${idx === imageModalIndex ? " isActive" : ""}`}
                    type="button"
                    onClick={() => setImageModalIndex(idx)}
                  >
                    <img
                      src={toRenderableMediaUrl(item.url)}
                      alt={item.caption || `Изображение ${idx + 1}`}
                    />
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {pendingDelete && (
        <div className="pg-modalBackdrop" onClick={() => setPendingDelete(null)}>
          <div className="pg-modal pn-deleteModal" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">Удалить файл</div>
                <div className="muted">Подтвердите удаление файла из карточки товара.</div>
              </div>
              <button className="btn" type="button" onClick={() => setPendingDelete(null)}>Закрыть</button>
            </div>
            <div className="pg-modalBody">
              <div className="pn-inlineNote pn-inlineNoteDanger">
                <div className="pn-inlineNoteDangerIcon" aria-hidden="true">!</div>
                <div>
                  Файл будет удален из системы. Это действие нельзя отменить. При необходимости файл придется загрузить заново.
                </div>
              </div>
              <div className="pn-alertActions">
                <button className="pn-cancelBtn" type="button" onClick={() => setPendingDelete(null)}>Отмена</button>
                <button className="pn-dangerBtn" type="button" onClick={confirmDeletePending}>Удалить</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {competitorModalKey && (
        <div className="pg-modalBackdrop" onClick={() => setCompetitorModalKey(null)}>
          <div className="pg-modal pn-linkModal" onClick={(e) => e.stopPropagation()}>
            <div className="pg-modalHead">
              <div>
                <div className="card-title">
                  {competitorModalKey === "restore" ? "Re:Store" : "Store77"}
                </div>
                <div className="muted">Укажите ссылку на товар конкурента.</div>
              </div>
              <button className="btn" type="button" onClick={() => setCompetitorModalKey(null)}>Закрыть</button>
            </div>
            <div className="pg-modalBody">
              <input
                className="pn-input"
                placeholder={competitorModalKey === "restore" ? "https://re-store.ru/..." : "https://store77.net/..."}
                value={competitorModalValue}
                onChange={(e) => setCompetitorModalValue(e.target.value)}
              />
              {!!competitorModalValue.trim() && (
                <div className="pn-inlineNote pn-inlineNoteSoft">Текущая ссылка: {competitorModalValue.trim()}</div>
              )}
              <div className="pn-alertActions">
                <button className="pn-cancelBtn" type="button" onClick={() => setCompetitorModalKey(null)}>Отмена</button>
                <button className="pn-saveBtn" type="button" onClick={saveCompetitorModal}>Сохранить</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
