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
 * 6 reserved meta keys injected by the backend extract_template task.
 * MUST be filtered from the field list in the UI (REQ-002-3 AC-11).
 * Single source of truth for both TS and Python — synced via
 * `scripts/codegen/gen_shared_schemas.py` → `packages/server-python/app/shared/schemas/document.py`.
 * When adding/removing keys: update this file, then re-run the codegen script
 * and commit the generated Python file.
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
