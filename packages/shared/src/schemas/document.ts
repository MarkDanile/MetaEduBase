import { z } from "zod";

export const JsonObjectSchema = z.record(z.string(), z.unknown());

export const FileStructuredDataSchema = z
  .object({
    full_text: z.string().optional(),
    section_count: z.number().optional(),
    template: JsonObjectSchema.optional(),
  })
  .passthrough();

export type FileStructuredData = z.infer<typeof FileStructuredDataSchema>;

export function parseFileStructuredData(value: unknown): FileStructuredData | null {
  if (value == null) return null;
  const result = FileStructuredDataSchema.safeParse(value);
  return result.success ? result.data : null;
}

export function getTemplateStructuredData(value: unknown): Record<string, unknown> | null {
  return parseFileStructuredData(value)?.template ?? null;
}
