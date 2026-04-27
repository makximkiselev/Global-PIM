export type ConnectorMethodStatus = "ok" | "warn" | "critical";

export type ConnectorMethodLike = {
  code: string;
  title: string;
  status: ConnectorMethodStatus;
  last_error?: string;
};

export type ConnectorIntent = {
  label: "Категории" | "Параметры" | "Товары" | "Медиа" | "Контур";
  impact: string;
};

export function methodIntent(method: Pick<ConnectorMethodLike, "code" | "title">): ConnectorIntent {
  const text = `${method.code} ${method.title}`.toLowerCase();
  if (text.includes("характер") || text.includes("attribute") || text.includes("param")) {
    return { label: "Параметры", impact: "Нужен для draft-моделей, инфо-моделей и сопоставления параметров." };
  }
  if (text.includes("дерев") || text.includes("categor")) {
    return { label: "Категории", impact: "Нужен для выбора веток и category mapping." };
  }
  if (text.includes("контент") || text.includes("товар") || text.includes("rating") || text.includes("статус")) {
    return { label: "Товары", impact: "Нужен для насыщения текущего каталога и проверки карточек." };
  }
  if (text.includes("generator") || text.includes("comfy")) {
    return { label: "Медиа", impact: "Влияет только на генерацию визуалов, не блокирует каталог и экспорт." };
  }
  return { label: "Контур", impact: "Проверка технической доступности источника." };
}

export function methodStatusLabel(status: ConnectorMethodStatus) {
  if (status === "ok") return "Готово";
  if (status === "warn") return "Есть предупреждение";
  return "Требует внимания";
}

export function humanConnectorError(raw: string) {
  const text = String(raw || "").trim();
  if (!text) return "Нет подробностей ошибки.";
  const lower = text.toLowerCase();
  if (lower.includes("descriptiontypeid") || lower.includes("description category")) {
    return "Ozon не смог загрузить параметры категории: в запрос попал пустой или некорректный description type id. Это блокирует автосбор параметров Ozon для новых моделей.";
  }
  if (lower.includes("failed to parse access token") || lower.includes("invalid number of segments")) {
    return "Ozon отклонил один из режимов авторизации. Нужно проверить, что используется Client ID + Api-Key, а не bearer token.";
  }
  if (lower.includes("comfyui_unreachable") || lower.includes("connection attempts failed")) {
    return "Генератор медиа недоступен. Это не блокирует каталог, модели и экспорт, но блокирует генерацию инфографики.";
  }
  if (text.length > 220) return `${text.slice(0, 220)}...`;
  return text;
}

export function connectorStatusClass(status: ConnectorMethodStatus) {
  return status === "ok" ? "ok" : status === "warn" ? "warn" : "critical";
}
