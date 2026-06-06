const API_ERROR_LABELS: Record<string, string> = {
  CATALOG_CATEGORY_NOT_FOUND: "Категория не найдена. Выберите категорию из дерева или вернитесь к сопоставлению категорий.",
  CATEGORY_NOT_DIRECTLY_MAPPED: "Для этой категории или ее родителя сначала нужна связка с категориями площадок.",
  AUTH_REQUIRED: "Сессия истекла или нет прав доступа. Войдите заново.",
  FORBIDDEN: "Нет прав на выполнение этого действия.",
  NOT_FOUND: "Запрошенные данные не найдены.",
};

function apiErrorMessage(body: string, status: number) {
  const raw = String(body || "").trim();
  let detail: unknown = raw;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown; message?: unknown; error?: unknown };
      detail = parsed.detail ?? parsed.message ?? parsed.error ?? raw;
    } catch {
      detail = raw;
    }
  }

  if (Array.isArray(detail)) {
    detail = detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg?: unknown }).msg || "");
        return "";
      })
      .filter(Boolean)
      .join("; ");
  } else if (detail && typeof detail === "object") {
    const record = detail as { code?: unknown; message?: unknown; detail?: unknown };
    detail = record.message ?? record.detail ?? record.code ?? JSON.stringify(detail);
  }

  const message = String(detail || "").trim();
  return API_ERROR_LABELS[message] || message || `HTTP ${status}`;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = path.startsWith("/api") ? path : `/api${path}`;

  const headers = new Headers(init.headers || {});
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const res = await fetch(url, { credentials: "include", ...init, headers });

  if (!res.ok) {
    if ((res.status === 401 || res.status === 403) && window.location.pathname !== "/login") {
      try {
        await fetch("/api/auth/logout", { method: "POST", credentials: "include", keepalive: true });
      } catch {
        // ignore redirect cleanup failure
      }
      const reason = res.status === 403 ? "denied=1" : "expired=1";
      window.location.href = `/login?${reason}`;
      throw new Error("AUTH_REQUIRED");
    }
    const text = await res.text().catch(() => "");
    throw new Error(apiErrorMessage(text, res.status));
  }

  // если вдруг 204
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return (null as unknown) as T;

  return res.json();
}
