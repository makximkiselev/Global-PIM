export type ProductFlowContext = {
  productId: string;
  categoryId: string;
  categoryName: string;
  title?: string;
  skuGt?: string;
  updatedAt?: string;
};

const PRODUCT_FLOW_CONTEXT_KEY = "smartpim_last_product_context_v1";

const emptyProductFlowContext: ProductFlowContext = {
  productId: "",
  categoryId: "",
  categoryName: "",
};

function clean(value: unknown) {
  return String(value ?? "").trim();
}

export function readProductFlowContext(): ProductFlowContext {
  if (typeof window === "undefined") return emptyProductFlowContext;
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PRODUCT_FLOW_CONTEXT_KEY) || "{}");
    return {
      productId: clean(parsed?.productId),
      categoryId: clean(parsed?.categoryId),
      categoryName: clean(parsed?.categoryName),
      title: clean(parsed?.title),
      skuGt: clean(parsed?.skuGt),
      updatedAt: clean(parsed?.updatedAt),
    };
  } catch {
    return emptyProductFlowContext;
  }
}

export function writeProductFlowContext(next: Partial<ProductFlowContext>) {
  if (typeof window === "undefined") return;
  const payload: ProductFlowContext = {
    productId: clean(next.productId),
    categoryId: clean(next.categoryId),
    categoryName: clean(next.categoryName),
    title: clean(next.title),
    skuGt: clean(next.skuGt),
    updatedAt: new Date().toISOString(),
  };
  if (!payload.productId && !payload.categoryId) return;
  try {
    window.localStorage.setItem(PRODUCT_FLOW_CONTEXT_KEY, JSON.stringify(payload));
  } catch {
    // Explicit URL params stay authoritative when browser storage is unavailable.
  }
}
