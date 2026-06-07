import { z } from "zod";

export const connectorStoreSchema = z
  .object({
    provider: z.enum(["yandex_market", "ozon"]),
    title: z.string().trim().min(1, "Заполните название магазина"),
    business_id: z.string().trim(),
    client_id: z.string().trim(),
    token: z.string().trim(),
    auth_mode: z.enum(["auto", "api-key", "oauth", "bearer"]),
    enabled: z.boolean(),
    export_enabled: z.boolean(),
    safe_test_enabled: z.boolean(),
    notes: z.string().trim(),
  })
  .superRefine((value, ctx) => {
    if (value.provider === "yandex_market" && !value.business_id) {
      ctx.addIssue({
        code: "custom",
        message: "Заполните ID кабинета",
        path: ["business_id"],
      });
    }
    if (value.provider === "ozon") {
      if (!value.client_id) {
        ctx.addIssue({
          code: "custom",
          message: "Заполните ID клиента",
          path: ["client_id"],
        });
      }
      if (!value.token) {
        ctx.addIssue({
          code: "custom",
          message: "Заполните ключ доступа",
          path: ["token"],
        });
      }
    }
  });

export type ConnectorStoreFormValues = z.infer<typeof connectorStoreSchema>;

export function defaultConnectorStoreValues(provider: ConnectorStoreFormValues["provider"]): ConnectorStoreFormValues {
  return {
    provider,
    title: "",
    business_id: "",
    client_id: "",
    token: "",
    auth_mode: provider === "ozon" ? "api-key" : "auto",
    enabled: true,
    export_enabled: false,
    safe_test_enabled: false,
    notes: "",
  };
}
