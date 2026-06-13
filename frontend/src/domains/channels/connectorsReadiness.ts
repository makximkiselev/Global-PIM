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

export type ConnectorBlockerAction = {
  label: string;
  href: string;
  hint?: string;
};

export function methodIntent(method: Pick<ConnectorMethodLike, "code" | "title">): ConnectorIntent {
  const text = `${method.code} ${method.title}`.toLowerCase();
  if (text.includes("характер") || text.includes("attribute") || text.includes("param")) {
    return { label: "Параметры", impact: "Нужен для моделей категорий и сопоставления параметров." };
  }
  if (text.includes("дерев") || text.includes("categor")) {
    return { label: "Категории", impact: "Нужен для выбора веток и сопоставления категорий площадок." };
  }
  if (text.includes("контент") || text.includes("товар") || text.includes("rating") || text.includes("статус")) {
    return { label: "Товары", impact: "Нужен для насыщения текущего каталога и проверки карточек." };
  }
  if (text.includes("media") || text.includes("image") || text.includes("generator") || text.includes("генератор")) {
    return { label: "Медиа", impact: "Влияет на проверку изображений, документов и порядка выгрузки." };
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
  if (lower.includes("yandex_import_stores_missing")) {
    return "Для Я.Маркета не выбран магазин импорта. Откройте вкладку «Магазины», добавьте или включите магазин и повторите процесс.";
  }
  if (lower.includes("ozon_import_stores_missing")) {
    return "Для Ozon не выбран магазин импорта. Откройте вкладку «Магазины», добавьте или включите магазин и повторите процесс.";
  }
  if (lower.includes("yandex_market_api_token_missing") || lower.includes("yandex_api_token_missing")) {
    return "Не задан ключ доступа Я.Маркета. Добавьте токен в настройках магазина или подключите новый магазин.";
  }
  if (lower.includes("ozon_api_key_missing") || lower.includes("ozon_client_id_missing")) {
    return "Не заполнены доступы Ozon. Проверьте Client ID и API Key в настройках магазина.";
  }
  if (lower.includes("insales") && (lower.includes("api_key_missing") || lower.includes("credentials_missing") || lower.includes("not_configured"))) {
    return "Не заполнены доступы InSales. Проверьте домен магазина, API login и API password.";
  }
  if (lower.includes("ozon_category_attributes_partial")) {
    const progress = text.match(/ozon_category_attributes_partial\s+(\d+)\/(\d+)/i);
    const suffix = progress ? ` Загружено ${progress[1]} из ${progress[2]} категорий.` : "";
    if (lower.includes("ozon_type_id_not_resolved")) {
      return `Ozon загрузил параметры не полностью: для одной из связанных категорий не найден type id.${suffix} Проверьте сопоставление категории Ozon и повторите импорт параметров.`;
    }
    return `Ozon загрузил параметры не полностью.${suffix} Откройте детали импорта, проверьте проблемные категории и повторите загрузку.`;
  }
  if (lower.includes("ozon_type_id_not_resolved")) {
    return "Ozon не смог определить type id для категории. Проверьте связь категории каталога с категорией Ozon и повторите импорт параметров.";
  }
  if (lower === "not_configured" || lower.includes("media_pipeline_not_ready")) {
    return "Медиа-пайплайн не подключен. Это не блокирует каталог, параметры и экспорт, но требует ручной проверки изображений и документов перед выгрузкой.";
  }
  if (lower.includes("descriptiontypeid") || lower.includes("description category")) {
    return "Ozon не смог загрузить параметры категории: в запрос попал пустой или некорректный description type id. Это блокирует автосбор параметров Ozon для новых моделей.";
  }
  if (lower.includes("failed to parse access token") || lower.includes("invalid number of segments")) {
    return "Ozon отклонил один из режимов авторизации. Нужно проверить, что используется Client ID + Api-Key, а не bearer token.";
  }
  if (lower.includes("media_pipeline_unreachable") || lower.includes("connection attempts failed")) {
    return "Медиа-пайплайн недоступен. Это не блокирует каталог, модели и экспорт, но требует ручной проверки изображений и документов перед выгрузкой.";
  }
  if (text.length > 220) return `${text.slice(0, 220)}...`;
  return text;
}

export function connectorBlockerAction(
  providerCode: string,
  method: Pick<ConnectorMethodLike, "code" | "last_error">,
): ConnectorBlockerAction {
  const provider = String(providerCode || "").trim();
  const code = String(method.code || "").trim();
  const error = String(method.last_error || "").trim();
  const lower = `${provider} ${code} ${error}`.toLowerCase();

  if (
    lower.includes("api_token_missing") ||
    lower.includes("api_key_missing") ||
    lower.includes("client_id_missing") ||
    lower.includes("import_stores_missing") ||
    lower.includes("credentials_missing")
  ) {
    return {
      label: "Открыть магазины",
      href: `/connectors/status?tab=stores&provider=${encodeURIComponent(provider || "")}`,
      hint: "Добавьте или проверьте магазин, ключи доступа и флаг участия в импорте/экспорте.",
    };
  }

  if (lower.includes("ozon_type_id_not_resolved") || lower.includes("ozon_category_attributes_partial")) {
    const providerCategoryId = error.match(/(?:^|[;|\s])(\d{5,})\s*:\s*(?:\d{3}:)?\s*ozon_type_id_not_resolved/i)?.[1] || "";
    const params = new URLSearchParams({ tab: "sources", provider: "ozon" });
    if (providerCategoryId) params.set("provider_category", providerCategoryId);
    return {
      label: providerCategoryId ? `Открыть категорию Ozon ${providerCategoryId}` : "Открыть сопоставление Ozon",
      href: `/sources?${params.toString()}`,
      hint: "Проверьте связь категории Ozon с веткой каталога, затем повторите импорт параметров.",
    };
  }

  if (provider === "media_pipeline" || lower.includes("media_pipeline") || lower.includes("not_configured")) {
    return {
      label: "Открыть медиа-проверку",
      href: "/images/infographics",
      hint: "Проверьте изображения, документы и порядок выгрузки без локальной генерации.",
    };
  }

  if (provider) {
    return {
      label: "Открыть источник",
      href: `/connectors/status?tab=marketplaces&provider=${encodeURIComponent(provider)}`,
      hint: "Проверьте процесс, доступы и последний запуск источника.",
    };
  }

  return {
    label: "Открыть источники",
    href: "/connectors/status?tab=marketplaces",
    hint: "Проверьте источник и повторите процесс после исправления.",
  };
}

export function connectorStatusClass(status: ConnectorMethodStatus) {
  return status === "ok" ? "ok" : status === "warn" ? "warn" : "critical";
}
