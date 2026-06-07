import { z } from "zod";

export const exportTargetSchema = z.object({
  provider: z.string().trim().min(1, "Выберите площадку"),
  store_ids: z.array(z.string().trim().min(1)).min(1, "Выберите хотя бы один магазин"),
});

export const exportSelectionSchema = z.object({
  selection: z.object({
    mode: z.enum(["mixed", "all"]),
    node_ids: z.array(z.string()),
    product_ids: z.array(z.string()),
    include_descendants: z.boolean(),
  }),
  targets: z.array(exportTargetSchema).min(1, "Выберите хотя бы один магазин для экспорта"),
  limit: z.number().int().min(1).max(500),
});

export type ExportSelectionPayload = z.infer<typeof exportSelectionSchema>;
