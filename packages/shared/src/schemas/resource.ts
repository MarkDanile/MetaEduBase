import { z } from "zod";

export const ResourceTypeEnum = z.enum([
  "courseware",
  "lesson_plan",
  "exercise",
  "case_study",
  "video",
  "document",
  "audio",
  "image",
]);

export const ResourceStatusEnum = z.enum([
  "raw",
  "parsed",
  "indexed",
  "archived",
]);

export const resourceSchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid(),
  title: z.string().min(1).max(300),
  description: z.string().max(2000).optional(),
  resourceType: ResourceTypeEnum,
  status: ResourceStatusEnum.default("raw"),
  domain: z.string().optional(),
  courseId: z.string().uuid().optional(),
  knowledgePointIds: z.array(z.string().uuid()).default([]),
  fileSize: z.number().int().nonnegative().optional(),
  fileType: z.string().max(50).optional(),
  storageKey: z.string().optional(),
  metadata: z.record(z.unknown()).default({}),
  uploadedBy: z.string().uuid(),
});

export type Resource = z.infer<typeof resourceSchema>;

export const resourceUploadSchema = z.object({
  title: z.string().min(1).max(300),
  domain: z.string().optional(),
  courseId: z.string().uuid().optional(),
  resourceType: ResourceTypeEnum.optional(),
});

export type ResourceUpload = z.infer<typeof resourceUploadSchema>;
