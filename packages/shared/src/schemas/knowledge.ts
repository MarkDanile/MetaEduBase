import { z } from "zod";

export const KnowledgeDomainEnum = z.enum([
  "electronics_info",
  "smart_manufacturing",
  "finance_commerce",
  "medical_health",
  "education_sports",
  "civil_engineering",
  "transportation",
  "agriculture",
  "art_design",
  "public_service",
]);

export const KnowledgeLevelEnum = z.enum([
  "professional",
  "course",
  "chapter",
  "knowledge_point",
  "skill_point",
  "operation_step",
]);

export const knowledgeNodeSchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid(),
  title: z.string().min(1).max(200),
  description: z.string().max(2000).optional(),
  domain: KnowledgeDomainEnum,
  level: KnowledgeLevelEnum,
  parentId: z.string().uuid().nullable(),
  tags: z.array(z.string()).default([]),
  metadata: z.record(z.unknown()).default({}),
});

export type KnowledgeNode = z.infer<typeof knowledgeNodeSchema>;

export const knowledgeSearchSchema = z.object({
  query: z.string().min(1),
  domain: KnowledgeDomainEnum.optional(),
  courseId: z.string().uuid().optional(),
  topK: z.number().int().min(1).max(50).default(5),
  searchMode: z.enum(["semantic", "keyword", "hybrid"]).default("hybrid"),
});

export type KnowledgeSearch = z.infer<typeof knowledgeSearchSchema>;
