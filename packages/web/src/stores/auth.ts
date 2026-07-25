import { defineStore } from "pinia";
import { ref, computed } from "vue";
import {
  aiChatSessionScope,
  clearAiChatSessionStorage,
} from "@/utils/aiChatSessionStorage";

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("metaedu_token"));
  const tenantId = ref<string | null>(localStorage.getItem("metaedu_tenant_id"));
  const userRole = ref<string | null>(localStorage.getItem("metaedu_role"));
  const userDomain = ref<string | null>(localStorage.getItem("metaedu_domain"));

  const isAuthenticated = computed(() => !!token.value);

  function setAuth(newToken: string, newTenantId: string, role: string, domain?: string) {
    if (aiChatSessionScope(token.value, tenantId.value)
      !== aiChatSessionScope(newToken, newTenantId)) {
      clearAiChatSessionStorage();
    }
    token.value = newToken;
    tenantId.value = newTenantId;
    userRole.value = role;
    userDomain.value = domain ?? null;
    localStorage.setItem("metaedu_token", newToken);
    localStorage.setItem("metaedu_tenant_id", newTenantId);
    localStorage.setItem("metaedu_role", role);
    if (domain) {
      localStorage.setItem("metaedu_domain", domain);
    } else {
      localStorage.removeItem("metaedu_domain");
    }
  }

  function clearAuth() {
    clearAiChatSessionStorage();
    token.value = null;
    tenantId.value = null;
    userRole.value = null;
    userDomain.value = null;
    localStorage.removeItem("metaedu_token");
    localStorage.removeItem("metaedu_tenant_id");
    localStorage.removeItem("metaedu_role");
    localStorage.removeItem("metaedu_domain");
  }

  return { token, tenantId, userRole, userDomain, isAuthenticated, setAuth, clearAuth };
});
