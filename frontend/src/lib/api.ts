function readableErrorMessage(status: number, text: string): string {
  const raw = String(text || "").trim();
  if (!raw) return `HTTP ${status}`;

  try {
    const parsed = JSON.parse(raw);
    const detail = parsed?.detail || parsed?.message || parsed?.error;
    if (typeof detail === "string" && detail.trim()) return detail.trim();
  } catch {
    // Plain text or an upstream HTML error page.
  }

  const withoutTags = raw.replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  if (status === 504 || /gateway time-?out/i.test(withoutTags)) {
    return "Источник или сервер не ответил вовремя. Повторите поиск позже.";
  }
  if (withoutTags) return withoutTags.slice(0, 240);
  return `HTTP ${status}`;
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
    throw new Error(readableErrorMessage(res.status, text));
  }

  // если вдруг 204
  const ct = res.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return (null as unknown) as T;

  return res.json();
}
