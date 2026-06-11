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

/**
 * 6 reserved meta keys that are injected by the backend extract_template task
 * and MUST be filtered from the field list in the UI (AC-11).
 * These must stay in sync with the backend `_TEMPLATE_META_KEYS` in
 * `packages/server-python/app/contexts/document/application/tasks/extract_template_prompts.py`.
 * Single source of truth: this constant. Backend sync is tracked in TD-043.
 */
export const TEMPLATE_META_RESERVED_KEYS: ReadonlySet<string> = new Set([
  "id",
  "version",
  "layer",
  "matched_type",
  "confidence",
  "reason",
] as const);

export function getTemplateStructuredData(value: unknown): Record<string, unknown> | null {
  return parseFileStructuredData(value)?.template ?? null;
}
