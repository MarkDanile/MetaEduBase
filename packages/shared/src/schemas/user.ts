import { z } from "zod";

export const RoleEnum = z.enum([
  "super_admin",
  "domain_expert",
  "teacher",
  "student",
  "harness_engineer",
  "system_ops",
]);

export const PermissionEnum = z.enum([
  "knowledge:read",
  "knowledge:write",
  "resource:upload",
  "resource:read",
  "skill:execute",
  "skill:configure",
  "plugin:use",
  "plugin:manage",
  "plugin:register",
  "course:read",
  "course:write",
  "user:manage",
  "tenant:manage",
  "infra:manage",
  "log:read",
]);

export const userSchema = z.object({
  id: z.string().uuid(),
  tenantId: z.string().uuid(),
  username: z.string().min(2).max(50),
  email: z.string().email().optional(),
  role: RoleEnum,
  domain: z.string().optional(),
  clearanceLevel: z.number().int().min(0).max(5).default(0),
  isActive: z.boolean().default(true),
});

export type User = z.infer<typeof userSchema>;

export const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(6),
  authMethod: z.enum(["local", "cas", "oauth2", "dingtalk"]).default("local"),
});

export type LoginRequest = z.infer<typeof loginSchema>;
