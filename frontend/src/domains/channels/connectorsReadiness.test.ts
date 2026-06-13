import { describe, expect, it } from "vitest";
import {
  connectorBlockerAction,
  connectorStatusClass,
  humanConnectorError,
  methodIntent,
  methodStatusLabel,
} from "./connectorsReadiness";

describe("connectorsReadiness", () => {
  it("classifies marketplace attribute imports as parameters, not category trees", () => {
    expect(methodIntent({ code: "ozon_category_attributes", title: "Импорт характеристик категорий" })).toEqual({
      label: "Параметры",
      impact: "Нужен для моделей категорий и сопоставления параметров.",
    });
  });

  it("classifies category tree, product content and media checks by operational impact", () => {
    expect(methodIntent({ code: "categories_tree", title: "Импорт дерева категорий" }).label).toBe("Категории");
    expect(methodIntent({ code: "offer_content", title: "Импорт контента товаров" }).label).toBe("Товары");
    expect(methodIntent({ code: "media_pipeline", title: "Проверка медиа" }).label).toBe("Медиа");
    expect(methodIntent({ code: "healthcheck", title: "Проверка доступности генератора" }).label).toBe("Медиа");
  });

  it("maps low-level connector errors to user-readable blockers", () => {
    expect(
      humanConnectorError(
        "OZON_CATEGORY_ATTRIBUTES_PARTIAL 28/29 imported; 17028924: 400: OZON_TYPE_ID_NOT_RESOLVED",
      ),
    ).toContain("Ozon загрузил параметры не полностью");
    expect(humanConnectorError("OZON_TYPE_ID_NOT_RESOLVED")).toContain("Проверьте связь категории каталога");
    expect(humanConnectorError("not_configured")).toContain("Медиа-пайплайн не подключен");
    expect(humanConnectorError("descriptionTypeId is required for description category")).toContain(
      "Ozon не смог загрузить параметры категории",
    );
    expect(humanConnectorError("Failed to parse access token: invalid number of segments")).toContain(
      "Client ID + Api-Key",
    );
    expect(humanConnectorError("MEDIA_PIPELINE_UNREACHABLE: connection attempts failed")).toContain(
      "Медиа-пайплайн недоступен",
    );
    expect(humanConnectorError("400: YANDEX_MARKET_API_TOKEN_MISSING")).toContain("ключ доступа Я.Маркета");
    expect(humanConnectorError("400: YANDEX_IMPORT_STORES_MISSING")).toContain("магазин импорта");
    expect(humanConnectorError("400: OZON_API_KEY_MISSING")).toContain("доступы Ozon");
  });

  it("builds blocker navigation to the place where the issue can be fixed", () => {
    const ozonAction = connectorBlockerAction("ozon", {
      code: "category_attributes",
      status: "warn",
      last_error: "OZON_CATEGORY_ATTRIBUTES_PARTIAL 28/29 imported; 17028924: 400: OZON_TYPE_ID_NOT_RESOLVED",
      title: "Импорт характеристик категорий",
    });

    expect(ozonAction.href).toContain("/sources?");
    expect(ozonAction.href).toContain("provider=ozon");
    expect(ozonAction.href).toContain("provider_category=17028924");
    expect(ozonAction.label).toContain("17028924");

    const mediaAction = connectorBlockerAction("media_pipeline", {
      code: "healthcheck",
      status: "warn",
      last_error: "not_configured",
      title: "Проверка доступности генератора",
    });

    expect(mediaAction.href).toBe("/images/infographics");
    expect(mediaAction.label).toContain("медиа");

    const storeAction = connectorBlockerAction("yandex_market", {
      code: "products_import",
      status: "critical",
      last_error: "400: YANDEX_IMPORT_STORES_MISSING",
      title: "Импорт товаров",
    });

    expect(storeAction.href).toContain("tab=stores");
    expect(storeAction.label).toBe("Открыть магазины");
  });

  it("keeps status labels and css classes stable", () => {
    expect(methodStatusLabel("ok")).toBe("Готово");
    expect(methodStatusLabel("warn")).toBe("Есть предупреждение");
    expect(methodStatusLabel("critical")).toBe("Требует внимания");
    expect(connectorStatusClass("ok")).toBe("ok");
    expect(connectorStatusClass("warn")).toBe("warn");
    expect(connectorStatusClass("critical")).toBe("critical");
  });
});
