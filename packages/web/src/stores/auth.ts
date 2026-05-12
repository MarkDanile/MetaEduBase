import { defineStore } from "pinia";
import { ref, computed } from "vue";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("metaedu_token"));
  const tenantId = ref<string | null>(localStorage.getItem("metaedu_tenant_id"));
  const userRole = ref<string | null>(null);
  const userDomain = ref<string | null>(null);

  const isAuthenticated = computed(() => !!token.value);

  function setAuth(newToken: string, newTenantId: string, role: string, domain?: string) {
    token.value = newToken;
    tenantId.value = newTenantId;
    userRole.value = role;
    userDomain.value = domain ?? null;
    localStorage.setItem("metaedu_token", newToken);
    localStorage.setItem("metaedu_tenant_id", newTenantId);
  }

  function clearAuth() {
    token.value = null;
    tenantId.value = null;
    userRole.value = null;
    userDomain.value = null;
    localStorage.removeItem("metaedu_token");
    localStorage.removeItem("metaedu_tenant_id");
  }

  return { token, tenantId, userRole, userDomain, isAuthenticated, setAuth, clearAuth };
});
