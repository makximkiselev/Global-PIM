function isYandexDiskUrl(url: string): boolean {
  try {
    const parsed = new URL(String(url || "").trim(), window.location.origin);
    const host = parsed.hostname.toLowerCase();
    return host.endsWith("disk.yandex.ru") || host.endsWith("yadi.sk");
  } catch {
    return false;
  }
}

export function toRenderableMediaUrl(url: string): string {
  const value = String(url || "").trim();
  if (!value) return "";
  if (!isYandexDiskUrl(value)) return value;
  return `/api/marketplaces/yandex/media-proxy?url=${encodeURIComponent(value)}`;
}
