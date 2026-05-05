import { describe, expect, it } from "vitest";
import {
  connectorStatusClass,
  humanConnectorError,
  methodIntent,
  methodStatusLabel,
} from "./connectorsReadiness";

describe("connectorsReadiness", () => {
  it("classifies marketplace attribute imports as parameters, not category trees", () => {
    expect(methodIntent({ code: "ozon_category_attributes", title: "Импорт характеристик категорий" })).toEqual({
      label: "Параметры",
      impact: "Нужен для draft-моделей, инфо-моделей и сопоставления параметров.",
    });
  });

  it("classifies category tree, product content and media checks by operational impact", () => {
    expect(methodIntent({ code: "categories_tree", title: "Импорт дерева категорий" }).label).toBe("Категории");
    expect(methodIntent({ code: "offer_content", title: "Импорт контента товаров" }).label).toBe("Товары");
    expect(methodIntent({ code: "comfyui_generator", title: "Проверка доступности генератора" }).label).toBe("Медиа");
  });

  it("maps low-level connector errors to user-readable blockers", () => {
    expect(humanConnectorError("descriptionTypeId is required for description category")).toContain(
      "Ozon не смог загрузить параметры категории",
    );
    expect(humanConnectorError("Failed to parse access token: invalid number of segments")).toContain(
      "Client ID + Api-Key",
    );
    expect(humanConnectorError("COMFYUI_UNREACHABLE: connection attempts failed")).toContain(
      "Генератор медиа недоступен",
    );
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
