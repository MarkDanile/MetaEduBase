<template>
  <div class="flex min-h-screen items-center justify-center bg-[var(--color-bg-base)]">
    <div class="ui-panel max-w-md w-full p-8 text-center">
      <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-[var(--color-danger-bg)] flex items-center justify-center">
        <ShieldX :size="28" :stroke-width="1.5" class="text-[var(--color-danger)]" />
      </div>
      <h1 class="text-[var(--text-page-title)] font-semibold mb-2">无权限访问</h1>
      <p class="text-[var(--color-ink-secondary)] mb-6">
        您当前角色无权访问此页面。如需权限，请联系管理员。
      </p>
      <button
        class="ui-btn ui-btn-primary"
        @click="$router.push('/')"
      >
        返回首页
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ShieldX } from "lucide-vue-next";
</script>
