export interface TenantContext {
  tenantId: string;
  schoolName: string;
  isolation: "shared" | "dedicated";
}
